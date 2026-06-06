import logging
import time
import urllib.request
from collections.abc import Callable

from backend.config import get_settings
from backend.database import check_database_health, get_migration_revision, session_scope
from backend.services.document_service import get_latest_index_job
from backend.services.index_worker import get_worker_status
from backend.services.rag_repository import get_faq_count, get_title_mapping
from backend.storage import check_storage_health


logger = logging.getLogger(__name__)
_status_cache = None
_status_cache_at = 0.0
_STATUS_CACHE_TTL_SECONDS = 5.0


def reset_status_cache() -> None:
    global _status_cache, _status_cache_at
    _status_cache = None
    _status_cache_at = 0.0


def get_full_system_status(check_vector_db_status: Callable[[], dict]) -> dict:
    global _status_cache, _status_cache_at
    now = time.time()
    if _status_cache is not None and now - _status_cache_at < _STATUS_CACHE_TTL_SECONDS:
        return dict(_status_cache)

    db_status_info = check_vector_db_status()
    db_status = db_status_info.get("status", "empty")
    raw_files = db_status_info.get("files", [])
    title_mapping = get_title_mapping()
    ollama_status = "offline"
    try:
        with urllib.request.urlopen(get_settings().ollama_base_url, timeout=0.5) as response:
            if response.status == 200:
                ollama_status = "online"
    except Exception:
        pass

    status = {
        "db_status": db_status,
        "pdf_count": len(raw_files),
        "faq_count": get_faq_count(),
        "ollama_status": ollama_status,
        "loaded_files": [title_mapping.get(filename, filename) for filename in raw_files],
        "document_management_mode": (
            "postgresql" if get_settings().database_enabled else "legacy"
        ),
    }
    try:
        status["postgresql"] = check_database_health()
        status["migration_revision"] = get_migration_revision()
        status["storage"] = check_storage_health()
        status["index_worker"] = get_worker_status()
        status["latest_index_job"] = None
        if get_settings().database_enabled and status["postgresql"].get("status") == "online":
            with session_scope() as session:
                job = get_latest_index_job(session)
                if job is not None:
                    status["latest_index_job"] = {
                        "id": job.id,
                        "trigger": job.trigger,
                        "status": job.status,
                        "created_at": job.created_at.isoformat() if job.created_at else None,
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    }
    except Exception:
        logger.exception("Unable to collect document management status")
        status["postgresql"] = {"status": "offline"}
        status["migration_revision"] = None
        status["storage"] = {"status": "unknown"}
        status["index_worker"] = {"enabled": False, "running": False, "name": None}
        status["latest_index_job"] = None

    _status_cache = dict(status)
    _status_cache_at = now
    return status
