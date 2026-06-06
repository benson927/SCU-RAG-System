from functools import lru_cache
import logging

from backend.config import get_settings

logger = logging.getLogger(__name__)


class S3Storage:
    def __init__(self):
        settings = get_settings()
        if not settings.storage_configured:
            raise RuntimeError("物件儲存環境變數尚未設定")
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("缺少 boto3 套件") from exc

        config = Config(
            connect_timeout=max(1, settings.storage_connect_timeout_seconds),
            read_timeout=max(1, settings.storage_read_timeout_seconds),
            retries={
                "total_max_attempts": max(1, settings.storage_max_attempts),
                "mode": "standard",
            },
            s3={"addressing_style": "path" if settings.storage_force_path_style else "virtual"},
        )
        self.bucket = settings.storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            region_name=settings.storage_region,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            config=config,
        )

    def upload_pdf(self, object_key: str, content: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=content,
            ContentType="application/pdf",
        )

    def download_file(self, object_key: str, destination: str) -> None:
        self.client.download_file(self.bucket, object_key, destination)

    def delete_file(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def health(self) -> dict:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return {"status": "online", "bucket_ready": True, "bucket": self.bucket}
        except Exception:
            logger.exception("Object storage health check failed")
            return {
                "status": "offline",
                "bucket_ready": False,
                "bucket": self.bucket,
            }


@lru_cache(maxsize=1)
def get_storage() -> S3Storage:
    return S3Storage()


def check_storage_health() -> dict:
    if not get_settings().storage_configured:
        return {"status": "not_configured", "bucket_ready": False}
    try:
        return get_storage().health()
    except Exception:
        logger.exception("Unable to initialize object storage health check")
        return {"status": "offline", "bucket_ready": False}
