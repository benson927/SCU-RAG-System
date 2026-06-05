import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", ""))
    admin_token_secret: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN_SECRET", ""))
    admin_token_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("ADMIN_TOKEN_TTL_SECONDS", "3600"))
    )
    max_pdf_size_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_PDF_SIZE_BYTES", str(20 * 1024 * 1024)))
    )
    storage_endpoint: str = field(default_factory=lambda: os.getenv("STORAGE_ENDPOINT", ""))
    storage_region: str = field(default_factory=lambda: os.getenv("STORAGE_REGION", "auto"))
    storage_bucket: str = field(default_factory=lambda: os.getenv("STORAGE_BUCKET", ""))
    storage_access_key: str = field(default_factory=lambda: os.getenv("STORAGE_ACCESS_KEY", ""))
    storage_secret_key: str = field(default_factory=lambda: os.getenv("STORAGE_SECRET_KEY", ""))
    storage_force_path_style: bool = field(
        default_factory=lambda: _env_bool("STORAGE_FORCE_PATH_STYLE", True)
    )
    index_worker_poll_seconds: float = field(
        default_factory=lambda: float(os.getenv("INDEX_WORKER_POLL_SECONDS", "2"))
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    )
    index_build_mode: str = field(
        default_factory=lambda: os.getenv("INDEX_BUILD_MODE", "chroma").strip().lower()
    )

    @property
    def database_enabled(self) -> bool:
        return bool(self.database_url)

    @property
    def storage_configured(self) -> bool:
        return bool(
            self.storage_bucket
            and self.storage_access_key
            and self.storage_secret_key
        )

    @property
    def token_secret(self) -> str:
        return self.admin_token_secret or self.admin_password


def get_settings() -> Settings:
    return Settings()
