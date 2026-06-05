import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Document, DocumentVersion, IndexJob
from backend.services import index_worker, rag_service


class FakeStorage:
    def download_file(self, object_key, destination):
        with open(destination, "wb") as handle:
            handle.write(b"%PDF-1.4 managed")


class FailingStorage:
    def download_file(self, object_key, destination):
        raise RuntimeError("download failed")


class FakeSession:
    def __init__(self, versions):
        self.versions = versions

    def scalars(self, _query):
        return self.versions


class TestIndexWorkerAtomicSync(unittest.TestCase):
    def make_version(self):
        document = SimpleNamespace(source_alias="legacy-law.pdf")
        return SimpleNamespace(
            document_id="document-id",
            id="version-id",
            title="測試法規",
            checksum="a" * 64,
            object_key="documents/law.pdf",
            document=document,
        )

    def patch_worker(self, temp_dir, versions):
        managed_dir = os.path.join(temp_dir, "data", "managed_documents")
        chroma_dir = os.path.join(temp_dir, "chroma_db")

        @contextmanager
        def fake_session_scope():
            yield FakeSession(versions)

        return managed_dir, chroma_dir, (
            patch.object(index_worker, "MANAGED_DATA_DIR", managed_dir),
            patch.object(index_worker, "session_scope", fake_session_scope),
            patch.object(index_worker, "get_storage", return_value=FakeStorage()),
            patch.object(rag_service, "CHROMA_DIR", chroma_dir),
        )

    def test_successful_sync_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            managed_dir, chroma_dir, patches = self.patch_worker(temp_dir, [self.make_version()])
            for active_patch in patches:
                active_patch.start()
            try:
                with patch.object(index_worker, "_build_vector_index") as build_index:
                    index_worker.rebuild_managed_index()
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()

            with open(os.path.join(managed_dir, "manifest.json"), "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertEqual(manifest["documents"][0]["source_alias"], "legacy-law.pdf")
            self.assertEqual(manifest["documents"][0]["title"], "測試法規")
            build_index.assert_called_once()
            build_path, build_manifest = build_index.call_args.args
            self.assertEqual(os.path.dirname(build_path), chroma_dir)
            self.assertTrue(os.path.basename(build_path).startswith(".chroma-staging-"))
            self.assertEqual(build_manifest, manifest)

    def test_index_failure_restores_previous_documents_and_chroma(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            managed_dir, chroma_dir, patches = self.patch_worker(temp_dir, [self.make_version()])
            os.makedirs(managed_dir)
            os.makedirs(chroma_dir)
            with open(os.path.join(managed_dir, "old.pdf"), "wb") as handle:
                handle.write(b"old managed")
            with open(os.path.join(chroma_dir, "old.index"), "w", encoding="utf-8") as handle:
                handle.write("old index")

            for active_patch in patches:
                active_patch.start()
            try:
                with patch.object(index_worker, "_build_vector_index", side_effect=RuntimeError("build failed")):
                    with self.assertRaisesRegex(RuntimeError, "build failed"):
                        index_worker.rebuild_managed_index()
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()

            self.assertTrue(os.path.exists(os.path.join(managed_dir, "old.pdf")))
            self.assertTrue(os.path.exists(os.path.join(chroma_dir, "old.index")))

    def test_download_failure_preserves_previous_documents_and_chroma(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            managed_dir, chroma_dir, patches = self.patch_worker(temp_dir, [self.make_version()])
            os.makedirs(managed_dir)
            os.makedirs(chroma_dir)
            with open(os.path.join(managed_dir, "old.pdf"), "wb") as handle:
                handle.write(b"old managed")
            with open(os.path.join(chroma_dir, "old.index"), "w", encoding="utf-8") as handle:
                handle.write("old index")

            patches = list(patches)
            patches[2] = patch.object(index_worker, "get_storage", return_value=FailingStorage())
            for active_patch in patches:
                active_patch.start()
            try:
                with self.assertRaisesRegex(RuntimeError, "download failed"):
                    index_worker.rebuild_managed_index()
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()

            self.assertTrue(os.path.exists(os.path.join(managed_dir, "old.pdf")))
            self.assertTrue(os.path.exists(os.path.join(chroma_dir, "old.index")))


class TestIndexWorkerStartupRecovery(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)

        @contextmanager
        def test_session_scope():
            session = self.Session()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self.session_patch = patch.object(index_worker, "session_scope", test_session_scope)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def add_published_version(self, session):
        document = Document(title="測試法規", source_alias="law.pdf")
        version = DocumentVersion(
            document=document,
            title=document.title,
            version_number="1.0",
            original_filename="law.pdf",
            object_key="documents/law.pdf",
            checksum="a" * 64,
            size_bytes=10,
            status="published",
        )
        session.add_all([document, version])

    def test_running_job_is_requeued_on_startup(self):
        with self.Session() as session:
            job = IndexJob(trigger="publish", status="running", error_message=None)
            session.add(job)
            session.commit()
            job_id = job.id

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            index_worker, "MANAGED_DATA_DIR", os.path.join(temp_dir, "managed")
        ), patch.object(index_worker, "CHROMA_DATA_DIR", os.path.join(temp_dir, "chroma")):
            index_worker._prepare_startup_jobs()

        with self.Session() as session:
            recovered = session.get(IndexJob, job_id)
            self.assertEqual(recovered.status, "pending")
            self.assertEqual(recovered.error_message, "服務重啟後重新排程")

    def test_existing_pending_job_prevents_duplicate_startup_job(self):
        with self.Session() as session:
            self.add_published_version(session)
            session.add(IndexJob(trigger="publish", status="pending"))
            session.commit()

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            index_worker, "MANAGED_DATA_DIR", os.path.join(temp_dir, "managed")
        ), patch.object(index_worker, "CHROMA_DATA_DIR", os.path.join(temp_dir, "chroma")):
            index_worker._prepare_startup_jobs()

        with self.Session() as session:
            self.assertEqual(session.query(IndexJob).count(), 1)


if __name__ == "__main__":
    unittest.main()
