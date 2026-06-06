import os
import time
import unittest
import uuid


RUN_INTEGRATION = os.getenv("RUN_COMPOSE_INTEGRATION") == "1"


@unittest.skipUnless(RUN_INTEGRATION, "set RUN_COMPOSE_INTEGRATION=1 with the Compose stack running")
class TestComposeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import boto3
        import httpx
        import psycopg

        cls.httpx = httpx
        cls.api_url = os.getenv("INTEGRATION_API_URL", "http://127.0.0.1:8000")
        cls.admin_password = os.getenv("ADMIN_PASSWORD", "scu-admin-dev")
        cls.database_url = os.getenv(
            "INTEGRATION_DATABASE_URL",
            os.getenv("DATABASE_URL", "postgresql://scu_rag:scu_rag_dev@127.0.0.1:5432/scu_rag"),
        )
        cls.bucket = os.getenv("STORAGE_BUCKET", "scu-law-documents")
        cls.s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv(
                "INTEGRATION_STORAGE_ENDPOINT",
                os.getenv("STORAGE_ENDPOINT", "http://127.0.0.1:9000"),
            ),
            region_name=os.getenv("STORAGE_REGION", "us-east-1"),
            aws_access_key_id=os.getenv(
                "STORAGE_ACCESS_KEY",
                os.getenv("MINIO_ROOT_USER", "scu_minio"),
            ),
            aws_secret_access_key=os.getenv(
                "STORAGE_SECRET_KEY",
                os.getenv("MINIO_ROOT_PASSWORD", "scu_minio_dev_password"),
            ),
        )
        cls.db = psycopg.connect(cls.database_url)
        deadline = time.time() + 60
        login = None
        while time.time() < deadline:
            try:
                login = httpx.post(
                    f"{cls.api_url}/api/admin/login",
                    json={"password": cls.admin_password},
                    timeout=5,
                )
                if login.is_success:
                    break
            except Exception:
                pass
            time.sleep(1)
        if login is None:
            raise RuntimeError("backend did not become available")
        login.raise_for_status()
        cls.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def wait_for_job(self, job_id):
        deadline = time.time() + 30
        final_job = None
        while time.time() < deadline:
            job = self.httpx.get(
                f"{self.api_url}/api/admin/index-jobs/{job_id}",
                headers=self.headers,
                timeout=10,
            )
            job.raise_for_status()
            final_job = job.json()
            if final_job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.5)
        self.assertIsNotNone(final_job)
        self.assertEqual(final_job["status"], "succeeded", final_job.get("error_message"))
        return final_job

    def test_postgres_minio_and_document_publish_flow(self):
        with self.db.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            self.assertEqual(cursor.fetchone()[0], "20260606_0003")

        self.s3.head_bucket(Bucket=self.bucket)
        unique = uuid.uuid4().hex[:10]
        response = self.httpx.post(
            f"{self.api_url}/api/admin/documents",
            headers=self.headers,
            data={"title": f"Integration Law {unique}", "version_number": "1.0"},
            files={
                "file": (
                    f"integration-{unique}.pdf",
                    f"%PDF-1.4 integration {unique}".encode(),
                    "application/pdf",
                )
            },
            timeout=15,
        )
        response.raise_for_status()
        version = response.json()["versions"][0]

        publish = self.httpx.post(
            f"{self.api_url}/api/admin/versions/{version['id']}/publish",
            headers=self.headers,
            timeout=10,
        )
        publish.raise_for_status()
        job_id = publish.json()["id"]
        self.wait_for_job(job_id)

        new_version = self.httpx.post(
            f"{self.api_url}/api/admin/documents/{response.json()['id']}/versions",
            headers=self.headers,
            data={"version_number": "2.0"},
            files={
                "file": (
                    f"integration-{unique}-v2.pdf",
                    f"%PDF-1.4 integration {unique} v2".encode(),
                    "application/pdf",
                )
            },
            timeout=15,
        )
        new_version.raise_for_status()
        version_two = next(item for item in new_version.json()["versions"] if item["version_number"] == "2.0")

        publish_two = self.httpx.post(
            f"{self.api_url}/api/admin/versions/{version_two['id']}/publish",
            headers=self.headers,
            timeout=10,
        )
        publish_two.raise_for_status()
        self.wait_for_job(publish_two.json()["id"])

        duplicate_version = self.httpx.post(
            f"{self.api_url}/api/admin/documents/{response.json()['id']}/versions",
            headers=self.headers,
            data={"version_number": "2.0"},
            files={"file": (f"integration-{unique}-duplicate.pdf", b"%PDF-1.4 other", "application/pdf")},
            timeout=15,
        )
        self.assertEqual(duplicate_version.status_code, 409)

        rollback = self.httpx.post(
            f"{self.api_url}/api/admin/versions/{version['id']}/rollback",
            headers=self.headers,
            timeout=10,
        )
        rollback.raise_for_status()
        self.wait_for_job(rollback.json()["id"])

        documents = self.httpx.get(
            f"{self.api_url}/api/admin/documents",
            headers=self.headers,
            timeout=10,
        )
        documents.raise_for_status()
        current = next(item for item in documents.json()["documents"] if item["id"] == response.json()["id"])
        statuses = {item["version_number"]: item["status"] for item in current["versions"]}
        self.assertEqual(statuses, {"1.0": "published", "2.0": "archived"})

        status = self.httpx.get(
            f"{self.api_url}/api/status",
            headers={"X-Request-ID": "integration-status-check"},
            timeout=10,
        )
        status.raise_for_status()
        self.assertEqual(status.headers["X-Request-ID"], "integration-status-check")
        payload = status.json()
        self.assertEqual(payload["postgresql"]["status"], "online")
        self.assertTrue(payload["storage"]["bucket_ready"])
        self.assertEqual(payload["migration_revision"], "20260606_0003")

        readiness = self.httpx.get(f"{self.api_url}/health/ready", timeout=10)
        readiness.raise_for_status()
        self.assertEqual(readiness.json()["status"], "ready")

        liveness = self.httpx.get(f"{self.api_url}/health/live", timeout=10)
        liveness.raise_for_status()
        self.assertEqual(liveness.json()["status"], "ok")
