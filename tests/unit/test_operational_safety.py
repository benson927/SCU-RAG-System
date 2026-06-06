import unittest
from unittest.mock import Mock, patch

from backend import database
from backend.logging_config import normalize_request_id
from backend.storage import S3Storage


class TestOperationalSafety(unittest.TestCase):
    def test_invalid_request_id_is_replaced(self):
        request_id = normalize_request_id("invalid request id\nwith control")
        self.assertNotEqual(request_id, "invalid request id\nwith control")
        self.assertEqual(len(request_id), 36)
        self.assertEqual(normalize_request_id("client-request:123"), "client-request:123")

    def test_database_health_does_not_expose_driver_error(self):
        engine = Mock()
        engine.connect.side_effect = RuntimeError("postgresql://user:secret@private-host/db")
        with (
            patch.object(database, "get_engine", return_value=engine),
            patch.object(database.logger, "exception"),
        ):
            result = database.check_database_health()
        self.assertEqual(result, {"status": "offline"})
        self.assertNotIn("secret", str(result))

    def test_storage_health_does_not_expose_provider_error(self):
        storage = S3Storage.__new__(S3Storage)
        storage.bucket = "private-bucket"
        storage.client = Mock()
        storage.client.head_bucket.side_effect = RuntimeError(
            "https://secret.internal/private-bucket"
        )
        with patch("backend.storage.logger.exception"):
            result = storage.health()
        self.assertEqual(
            result,
            {
                "status": "offline",
                "bucket_ready": False,
                "bucket": "private-bucket",
            },
        )
        self.assertNotIn("secret.internal", str(result))


if __name__ == "__main__":
    unittest.main()
