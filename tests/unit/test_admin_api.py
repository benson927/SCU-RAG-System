import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.admin_router import router
from backend.auth import create_admin_token
from backend.database import Base, get_session
from backend.models import IndexJob
from backend.security import reset_rate_limits
from backend.services import document_service


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def upload_pdf(self, object_key, content):
        self.objects[object_key] = content

    def delete_file(self, object_key):
        self.objects.pop(object_key, None)


class TestAdminApi(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "ADMIN_PASSWORD": "test-password",
                "ADMIN_TOKEN_SECRET": "test-secret",
                "ADMIN_TOKEN_TTL_SECONDS": "60",
                "MAX_PDF_SIZE_BYTES": "32",
                "ADMIN_LOGIN_RATE_LIMIT": "100",
            },
            clear=False,
        )
        self.environment.start()
        reset_rate_limits()
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.storage = FakeStorage()
        self.storage_patch = patch.object(document_service, "get_storage", return_value=self.storage)
        self.wake_patch = patch("backend.api.admin_router.wake_index_worker")
        self.storage_patch.start()
        self.wake_patch.start()

        app = FastAPI()
        app.include_router(router, prefix="/api/admin")

        def override_session():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.wake_patch.stop()
        self.storage_patch.stop()
        self.environment.stop()
        reset_rate_limits()

    def login_headers(self):
        response = self.client.post("/api/admin/login", json={"password": "test-password"})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def upload_document(self, headers, title="測試法規", version="1.0"):
        return self.client.post(
            "/api/admin/documents",
            headers=headers,
            data={"title": title, "version_number": version},
            files={"file": ("law.pdf", b"%PDF-1.4 valid", "application/pdf")},
        )

    def test_login_and_authorization_errors(self):
        self.assertEqual(
            self.client.post("/api/admin/login", json={"password": "wrong"}).status_code,
            401,
        )
        self.assertEqual(self.client.get("/api/admin/documents").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/admin/documents",
                headers={"Authorization": "Bearer invalid"},
            ).status_code,
            401,
        )
        expired, _ = create_admin_token(now=1)
        self.assertEqual(
            self.client.get(
                "/api/admin/documents",
                headers={"Authorization": f"Bearer {expired}"},
            ).status_code,
            401,
        )
        self.assertEqual(self.client.get("/api/admin/documents", headers=self.login_headers()).status_code, 200)

    def test_login_rate_limit(self):
        reset_rate_limits()
        with patch.dict(os.environ, {"ADMIN_LOGIN_RATE_LIMIT": "2"}, clear=False):
            self.assertEqual(
                self.client.post("/api/admin/login", json={"password": "wrong"}).status_code,
                401,
            )
            self.assertEqual(
                self.client.post("/api/admin/login", json={"password": "wrong"}).status_code,
                401,
            )
            response = self.client.post("/api/admin/login", json={"password": "wrong"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_pdf_validation_and_valid_multipart_upload(self):
        headers = self.login_headers()
        wrong_mime = self.client.post(
            "/api/admin/documents",
            headers=headers,
            data={"title": "錯誤 MIME", "version_number": "1"},
            files={"file": ("law.pdf", b"%PDF-1.4", "text/plain")},
        )
        self.assertEqual(wrong_mime.status_code, 400)

        wrong_header = self.client.post(
            "/api/admin/documents",
            headers=headers,
            data={"title": "錯誤檔頭", "version_number": "1"},
            files={"file": ("law.pdf", b"not-pdf", "application/pdf")},
        )
        self.assertEqual(wrong_header.status_code, 400)

        too_large = self.client.post(
            "/api/admin/documents",
            headers=headers,
            data={"title": "過大", "version_number": "1"},
            files={"file": ("law.pdf", b"%PDF-" + b"x" * 40, "application/pdf")},
        )
        self.assertEqual(too_large.status_code, 413)

        valid = self.upload_document(headers)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["versions"][0]["status"], "draft")

    def test_document_lifecycle_and_failed_job_retry(self):
        headers = self.login_headers()
        created = self.upload_document(headers)
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        document_id = payload["id"]
        first_version = payload["versions"][0]["id"]

        published = self.client.post(
            f"/api/admin/versions/{first_version}/publish",
            headers=headers,
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["status"], "pending")

        archived = self.client.post(
            f"/api/admin/versions/{first_version}/archive",
            headers=headers,
        )
        self.assertEqual(archived.status_code, 200)
        rolled_back = self.client.post(
            f"/api/admin/versions/{first_version}/rollback",
            headers=headers,
        )
        self.assertEqual(rolled_back.status_code, 200)

        draft = self.client.post(
            f"/api/admin/documents/{document_id}/versions",
            headers=headers,
            data={"version_number": "2.0"},
            files={"file": ("law-v2.pdf", b"%PDF-1.4 version two", "application/pdf")},
        )
        self.assertEqual(draft.status_code, 200)
        second_version = next(
            item["id"] for item in draft.json()["versions"] if item["version_number"] == "2.0"
        )
        self.assertEqual(
            self.client.delete(f"/api/admin/versions/{second_version}", headers=headers).status_code,
            204,
        )

        with self.Session() as session:
            failed = IndexJob(trigger="publish", status="failed", error_message="boom")
            session.add(failed)
            session.commit()
            failed_id = failed.id
        retried = self.client.post(
            f"/api/admin/index-jobs/{failed_id}/retry",
            headers=headers,
        )
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["status"], "pending")
        self.assertNotEqual(retried.json()["id"], failed_id)


if __name__ == "__main__":
    unittest.main()
