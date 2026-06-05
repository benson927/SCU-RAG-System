import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.auth import create_admin_token, decode_admin_token, verify_admin_password
from backend.database import Base
from backend.models import DocumentVersion, IndexJob
from backend.services import document_service
from backend.services.document_service import (
    archive_version,
    create_document_with_version,
    delete_draft_version,
    publish_version,
    retry_failed_index_job,
    validate_pdf,
)


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.fail_delete = False

    def upload_pdf(self, object_key, content):
        self.objects[object_key] = content

    def delete_file(self, object_key):
        if self.fail_delete:
            raise RuntimeError("storage unavailable")
        self.objects.pop(object_key)


class TestAdminAuth(unittest.TestCase):
    def test_admin_token_signature_and_expiry(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_PASSWORD": "demo-password",
                "ADMIN_TOKEN_SECRET": "test-secret",
                "ADMIN_TOKEN_TTL_SECONDS": "60",
            },
            clear=False,
        ):
            self.assertTrue(verify_admin_password("demo-password"))
            self.assertFalse(verify_admin_password("wrong"))
            token, expires_at = create_admin_token(now=1000)
            self.assertEqual(expires_at, 1060)
            self.assertEqual(decode_admin_token(token, now=1059)["sub"], "admin")
            with self.assertRaises(ValueError):
                decode_admin_token(token, now=1060)


class TestDocumentLifecycle(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.storage = FakeStorage()
        self.storage_patch = patch.object(document_service, "get_storage", return_value=self.storage)
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()

    def test_pdf_validation_rejects_non_pdf_content(self):
        with self.assertRaises(HTTPException) as raised:
            validate_pdf("fake.pdf", "application/pdf", b"not a pdf")
        self.assertEqual(raised.exception.status_code, 400)

    def test_publish_archive_and_rollback_keep_one_active_version(self):
        session = self.Session()
        document = create_document_with_version(
            session,
            title="測試法規",
            version_number="1.0",
            effective_date=None,
            filename="law.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 first",
        )
        first = document.versions[0]
        publish_version(session, first.id, allowed_statuses={"draft"})

        second = DocumentVersion(
            document_id=document.id,
            title=document.title,
            version_number="2.0",
            original_filename="law-v2.pdf",
            object_key="documents/v2.pdf",
            checksum="2" * 64,
            size_bytes=20,
            status="draft",
        )
        session.add(second)
        session.commit()
        publish_version(session, second.id, allowed_statuses={"draft"})

        published = session.query(DocumentVersion).filter_by(document_id=document.id, status="published").all()
        self.assertEqual([version.id for version in published], [second.id])
        self.assertEqual(session.get(DocumentVersion, first.id).status, "archived")

        archive_version(session, second.id)
        publish_version(session, first.id, trigger="rollback", allowed_statuses={"archived"})
        self.assertEqual(session.get(DocumentVersion, first.id).status, "published")
        self.assertEqual(session.get(DocumentVersion, second.id).status, "archived")

    def test_only_draft_can_be_deleted(self):
        session = self.Session()
        document = create_document_with_version(
            session,
            title="草稿法規",
            version_number="draft-1",
            effective_date=None,
            filename="draft.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 draft",
        )
        version = document.versions[0]
        delete_draft_version(session, version.id)
        self.assertIsNone(session.get(DocumentVersion, version.id))

    def test_duplicate_checksum_cleans_uploaded_object(self):
        session = self.Session()
        content = b"%PDF-1.4 duplicate"
        create_document_with_version(
            session,
            title="第一份法規",
            version_number="1.0",
            effective_date=None,
            filename="first.pdf",
            content_type="application/pdf",
            content=content,
        )
        original_keys = set(self.storage.objects)

        with self.assertRaises(HTTPException) as raised:
            create_document_with_version(
                session,
                title="第二份法規",
                version_number="1.0",
                effective_date=None,
                filename="second.pdf",
                content_type="application/pdf",
                content=content,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(set(self.storage.objects), original_keys)

    def test_database_commit_failure_cleans_uploaded_object(self):
        session = self.Session()
        with patch.object(session, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                create_document_with_version(
                    session,
                    title="交易失敗法規",
                    version_number="1.0",
                    effective_date=None,
                    filename="failed.pdf",
                    content_type="application/pdf",
                    content=b"%PDF-1.4 commit failure",
                )
        self.assertEqual(self.storage.objects, {})

    def test_storage_delete_failure_keeps_draft_record(self):
        session = self.Session()
        document = create_document_with_version(
            session,
            title="不可刪除草稿",
            version_number="1.0",
            effective_date=None,
            filename="draft.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 keep",
        )
        version = document.versions[0]
        self.storage.fail_delete = True

        with self.assertRaises(HTTPException) as raised:
            delete_draft_version(session, version.id)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIsNotNone(session.get(DocumentVersion, version.id))

    def test_pending_index_jobs_are_coalesced(self):
        session = self.Session()
        document = create_document_with_version(
            session,
            title="合併工作法規",
            version_number="1.0",
            effective_date=None,
            filename="coalesce.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 coalesce",
        )
        version = document.versions[0]
        first_job = publish_version(session, version.id, allowed_statuses={"draft"})
        second_job = archive_version(session, version.id)

        self.assertEqual(first_job.id, second_job.id)
        self.assertEqual(session.query(IndexJob).count(), 1)

    def test_failed_index_job_retry_keeps_audit_record(self):
        session = self.Session()
        failed = IndexJob(trigger="publish", status="failed", error_message="boom")
        session.add(failed)
        session.commit()

        retried = retry_failed_index_job(session, failed.id)

        self.assertNotEqual(retried.id, failed.id)
        self.assertEqual(retried.status, "pending")
        self.assertEqual(session.query(IndexJob).count(), 2)


if __name__ == "__main__":
    unittest.main()
