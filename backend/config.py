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
    database_connect_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "10"))
    )
    database_pool_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "10"))
    )
    database_pool_size: int = field(
        default_factory=lambda: int(os.getenv("DATABASE_POOL_SIZE", "5"))
    )
    database_max_overflow: int = field(
        default_factory=lambda: int(os.getenv("DATABASE_MAX_OVERFLOW", "5"))
    )
    max_query_length: int = field(
        default_factory=lambda: int(os.getenv("MAX_QUERY_LENGTH", "1000"))
    )
    rag_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("RAG_TIMEOUT_SECONDS", "120"))
    )
    rag_max_concurrency: int = field(
        default_factory=lambda: int(os.getenv("RAG_MAX_CONCURRENCY", "2"))
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    )
    rag_rate_limit: int = field(
        default_factory=lambda: int(os.getenv("RAG_RATE_LIMIT", "20"))
    )
    admin_login_rate_limit: int = field(
        default_factory=lambda: int(os.getenv("ADMIN_LOGIN_RATE_LIMIT", "5"))
    )
    trust_proxy_headers: bool = field(
        default_factory=lambda: _env_bool("TRUST_PROXY_HEADERS", False)
    )
    storage_endpoint: str = field(default_factory=lambda: os.getenv("STORAGE_ENDPOINT", ""))
    storage_region: str = field(default_factory=lambda: os.getenv("STORAGE_REGION", "auto"))
    storage_bucket: str = field(default_factory=lambda: os.getenv("STORAGE_BUCKET", ""))
    storage_access_key: str = field(default_factory=lambda: os.getenv("STORAGE_ACCESS_KEY", ""))
    storage_secret_key: str = field(default_factory=lambda: os.getenv("STORAGE_SECRET_KEY", ""))
    storage_force_path_style: bool = field(
        default_factory=lambda: _env_bool("STORAGE_FORCE_PATH_STYLE", True)
    )
    storage_connect_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("STORAGE_CONNECT_TIMEOUT_SECONDS", "5"))
    )
    storage_read_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("STORAGE_READ_TIMEOUT_SECONDS", "30"))
    )
    storage_max_attempts: int = field(
        default_factory=lambda: int(os.getenv("STORAGE_MAX_ATTEMPTS", "3"))
    )
    index_worker_poll_seconds: float = field(
        default_factory=lambda: float(os.getenv("INDEX_WORKER_POLL_SECONDS", "2"))
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    )
    ollama_chat_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_CHAT_MODEL", "gemma3")
    )
    ollama_embedding_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    )
    ollama_request_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "120"))
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
