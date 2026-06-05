import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Document, DocumentVersion, IndexJob
from backend.scripts import import_legacy_data
from backend.services import document_service


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.fail_upload = False

    def upload_pdf(self, object_key, content):
        if self.fail_upload:
            raise RuntimeError("upload failed")
        self.objects[object_key] = content

    def delete_file(self, object_key):
        self.objects.pop(object_key, None)


class TestLegacyImporter(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.storage = FakeStorage()

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

        self.session_patch = patch.object(import_legacy_data, "session_scope", test_session_scope)
        self.storage_patch = patch.object(document_service, "get_storage", return_value=self.storage)
        self.wake_patch = patch.object(import_legacy_data, "wake_index_worker")
        self.session_patch.start()
        self.storage_patch.start()
        self.wake = self.wake_patch.start()

    def tearDown(self):
        self.wake_patch.stop()
        self.storage_patch.stop()
        self.session_patch.stop()

    def make_fixture(self, root: Path):
        data_dir = root / "data"
        data_dir.mkdir()
        (data_dir / "legacy.pdf").write_bytes(b"%PDF-1.4 legacy")
        mapping = root / "titles.json"
        mapping.write_text(json.dumps({"legacy.pdf": "Legacy Law"}), encoding="utf-8")
        return data_dir, mapping

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir, mapping = self.make_fixture(Path(temp_dir))
            result = import_legacy_data.import_legacy_data(data_dir, mapping, publish=False)
        self.assertEqual(result["items"][0]["action"], "dry-run")
        with self.Session() as session:
            self.assertEqual(session.query(Document).count(), 0)
            self.assertEqual(session.query(IndexJob).count(), 0)
        self.assertEqual(self.storage.objects, {})

    def test_publish_creates_one_job_and_rerun_skips_checksum(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir, mapping = self.make_fixture(Path(temp_dir))
            first = import_legacy_data.import_legacy_data(data_dir, mapping, publish=True)
            second = import_legacy_data.import_legacy_data(data_dir, mapping, publish=True)

        self.assertEqual(first["imported"], 1)
        self.assertEqual(second["skipped"], 1)
        with self.Session() as session:
            self.assertEqual(session.query(Document).count(), 1)
            self.assertEqual(session.query(DocumentVersion).count(), 1)
            self.assertEqual(session.query(IndexJob).count(), 1)
        self.assertEqual(len(self.storage.objects), 1)
        self.wake.assert_called_once()

    def test_storage_failure_does_not_create_database_rows(self):
        self.storage.fail_upload = True
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir, mapping = self.make_fixture(Path(temp_dir))
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                import_legacy_data.import_legacy_data(data_dir, mapping, publish=True)

        with self.Session() as session:
            self.assertEqual(session.query(Document).count(), 0)
            self.assertEqual(session.query(DocumentVersion).count(), 0)
            self.assertEqual(session.query(IndexJob).count(), 0)
        self.assertEqual(self.storage.objects, {})


if __name__ == "__main__":
    unittest.main()
