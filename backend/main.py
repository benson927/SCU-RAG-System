import logging
import os
import time
from contextlib import asynccontextmanager


_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CURRENT_DIR)
_env_path = os.path.join(_PROJECT_ROOT, ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.admin_router import router as admin_router
from backend.api.router import router as rag_router
from backend.config import get_settings
from backend.database import check_database_health, get_migration_revision
from backend.logging_config import (
    configure_logging,
    normalize_request_id,
    request_id_context,
)
from backend.services.index_worker import start_index_worker, stop_index_worker
from backend.storage import check_storage_health


configure_logging()
logger = logging.getLogger(__name__)
CURRENT_MIGRATION_REVISION = "20260606_0003"

_default_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
] or _default_cors_origins


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_index_worker()
    try:
        yield
    finally:
        stop_index_worker()


app = FastAPI(
    title="SCU Law RAG System API",
    description="自架式法規 RAG 與文件版本管理 API。",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request, call_next):
    request_id = normalize_request_id(request.headers.get("X-Request-ID"))
    token = request_id_context.set(request_id)
    started_at = time.monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info(
            "HTTP request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": int((time.monotonic() - started_at) * 1000),
            },
        )
        request_id_context.reset(token)


app.include_router(rag_router, prefix="/api", tags=["RAG"])
app.include_router(admin_router, prefix="/api/admin", tags=["Document Admin"])


@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "FastAPI RAG 後端伺服器運行中。請訪問 /docs 查看 API 文件。",
    }


@app.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def health_ready():
    settings = get_settings()
    checks = {}
    ready = True
    if settings.database_enabled:
        checks["postgresql"] = check_database_health()
        checks["migration_revision"] = get_migration_revision()
        checks["storage"] = check_storage_health()
        checks["admin_auth_configured"] = bool(
            settings.admin_password and settings.admin_token_secret
        )
        ready = (
            checks["postgresql"].get("status") == "online"
            and checks["storage"].get("bucket_ready") is True
            and checks["migration_revision"] == CURRENT_MIGRATION_REVISION
            and checks["admin_auth_configured"]
        )
    else:
        checks["mode"] = "legacy"
    payload = {"status": "ready" if ready else "not_ready", "checks": checks}
    return JSONResponse(payload, status_code=200 if ready else 503)
