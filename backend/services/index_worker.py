import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.database import session_scope
from backend.models import DocumentVersion, IndexJob
from backend.services.document_service import enqueue_index_job
from backend.storage import get_storage


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANAGED_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "managed_documents")
CHROMA_DATA_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")
MANAGED_MANIFEST_NAME = "manifest.json"
CHROMA_MANIFEST_NAME = "managed_manifest.json"

_worker_thread = None
_stop_event = threading.Event()
_wake_event = threading.Event()
_rebuild_lock = threading.RLock()
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def wake_index_worker() -> None:
    _wake_event.set()


def get_worker_status() -> dict:
    return {
        "enabled": get_settings().database_enabled,
        "running": bool(_worker_thread and _worker_thread.is_alive()),
        "name": _worker_thread.name if _worker_thread and _worker_thread.is_alive() else None,
    }


def start_index_worker() -> None:
    global _worker_thread
    if not get_settings().database_enabled:
        return
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="document-index-worker", daemon=True)
    _worker_thread.start()


def stop_index_worker() -> None:
    _stop_event.set()
    _wake_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=5)


def _worker_loop() -> None:
    poll_seconds = get_settings().index_worker_poll_seconds
    prepared = False
    while not _stop_event.is_set():
        try:
            if not prepared:
                _prepare_startup_jobs()
                prepared = True
            job_id = _claim_next_job()
            if job_id:
                _process_job(job_id)
                continue
        except Exception:
            logger.exception("Index worker temporarily unavailable")
        _wake_event.wait(timeout=poll_seconds)
        _wake_event.clear()


def _prepare_startup_jobs() -> None:
    with session_scope() as session:
        session.execute(
            update(IndexJob)
            .where(IndexJob.status == "running")
            .values(status="pending", started_at=None, error_message="服務重啟後重新排程")
        )
        published_version = session.scalar(
            select(DocumentVersion.id)
            .where(DocumentVersion.status == "published")
            .limit(1)
        )
        active_job = session.scalar(
            select(IndexJob.id)
            .where(IndexJob.status.in_(["pending", "running"]))
            .limit(1)
        )
        index_incomplete = not _index_artifacts_ready()
        if published_version and not active_job and index_incomplete:
            enqueue_index_job(session, "startup_rebuild")


def _load_json_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _index_artifacts_ready() -> bool:
    managed_manifest = _load_json_file(
        os.path.join(MANAGED_DATA_DIR, MANAGED_MANIFEST_NAME)
    )
    chroma_manifest = _load_json_file(
        os.path.join(CHROMA_DATA_DIR, CHROMA_MANIFEST_NAME)
    )
    if not managed_manifest or not chroma_manifest:
        return False

    generation = managed_manifest.get("generation")
    documents = managed_manifest.get("documents")
    if (
        not isinstance(generation, str)
        or not generation
        or generation != chroma_manifest.get("generation")
        or not isinstance(documents, list)
    ):
        return False

    if not os.path.isfile(os.path.join(CHROMA_DATA_DIR, "db_meta.json")):
        return False
    for document in documents:
        filename = document.get("filename") if isinstance(document, dict) else None
        if (
            not isinstance(filename, str)
            or os.path.basename(filename) != filename
            or not os.path.isfile(os.path.join(MANAGED_DATA_DIR, filename))
        ):
            return False
    return True


def _claim_next_job() -> str | None:
    with session_scope() as session:
        job = session.scalar(
            select(IndexJob)
            .where(IndexJob.status == "pending")
            .order_by(IndexJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "running"
        job.started_at = _utcnow()
        job.error_message = None
        session.flush()
        return job.id


def _process_job(job_id: str) -> None:
    try:
        rebuild_managed_index()
    except Exception as exc:
        logger.exception("Index job failed", extra={"job_id": job_id})
        with session_scope() as session:
            job = session.get(IndexJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)[:4000]
                job.finished_at = _utcnow()
        return

    with session_scope() as session:
        job = session.get(IndexJob, job_id)
        if job is not None:
            job.status = "succeeded"
            job.finished_at = _utcnow()


def _create_staging_directory(root: str, prefix: str) -> str:
    os.makedirs(root, exist_ok=True)
    staging = os.path.join(root, f".{prefix}-staging-{int(time.time() * 1000)}")
    os.makedirs(staging, exist_ok=False)
    return staging


def _swap_directory_contents(root: str, staging: str, backup_name: str) -> str:
    backup = os.path.join(root, backup_name)
    if os.path.exists(backup):
        shutil.rmtree(backup)
    os.makedirs(backup)

    excluded = {os.path.basename(staging), backup_name}
    for name in os.listdir(root):
        if name not in excluded:
            os.replace(os.path.join(root, name), os.path.join(backup, name))
    for name in os.listdir(staging):
        os.replace(os.path.join(staging, name), os.path.join(root, name))
    os.rmdir(staging)
    return backup


def _restore_directory_contents(root: str, backup: str | None) -> None:
    if not backup or not os.path.exists(backup):
        return
    backup_name = os.path.basename(backup)
    for name in os.listdir(root):
        if name != backup_name:
            path = os.path.join(root, name)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
    for name in os.listdir(backup):
        os.replace(os.path.join(backup, name), os.path.join(root, name))
    os.rmdir(backup)


def rebuild_managed_index() -> None:
    from backend.services.rag_service import CHROMA_DIR, _clear_runtime_caches

    with _rebuild_lock:
        with session_scope() as session:
            versions = list(
                session.scalars(
                    select(DocumentVersion)
                    .where(DocumentVersion.status == "published")
                    .options(selectinload(DocumentVersion.document))
                    .order_by(DocumentVersion.document_id)
                )
            )

        staging = _create_staging_directory(MANAGED_DATA_DIR, "managed")
        managed_backup = None
        chroma_staging = None
        chroma_backup = None
        mapping = {}
        manifest = {
            "version": 1,
            "generation": str(uuid.uuid4()),
            "documents": [],
        }
        try:
            storage = get_storage() if versions else None
            for version in versions:
                filename = f"{version.document_id}_{version.id}.pdf"
                destination = os.path.join(staging, filename)
                storage.download_file(version.object_key, destination)
                mapping[filename] = version.title
                manifest["documents"].append(
                    {
                        "document_id": version.document_id,
                        "version_id": version.id,
                        "filename": filename,
                        "title": version.title,
                        "source_alias": version.document.source_alias,
                        "checksum": version.checksum,
                    }
                )

            with open(os.path.join(staging, "title_mapping.json"), "w", encoding="utf-8") as handle:
                json.dump(mapping, handle, ensure_ascii=False, indent=2)
            with open(os.path.join(staging, MANAGED_MANIFEST_NAME), "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2)

            managed_backup = _swap_directory_contents(
                MANAGED_DATA_DIR,
                staging,
                ".managed-backup",
            )

            _clear_runtime_caches(clear_db=True)
            chroma_staging = _create_staging_directory(CHROMA_DIR, "chroma")
            _build_vector_index(chroma_staging, manifest)
            with open(
                os.path.join(chroma_staging, CHROMA_MANIFEST_NAME),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    {
                        "version": manifest["version"],
                        "generation": manifest["generation"],
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
            chroma_backup = _swap_directory_contents(
                CHROMA_DIR,
                chroma_staging,
                ".chroma-backup",
            )
            _clear_runtime_caches(clear_db=True)
            shutil.rmtree(managed_backup, ignore_errors=True)
            shutil.rmtree(chroma_backup, ignore_errors=True)
        except Exception:
            if os.path.exists(staging):
                shutil.rmtree(staging, ignore_errors=True)
            if chroma_staging and os.path.exists(chroma_staging):
                shutil.rmtree(chroma_staging, ignore_errors=True)
            _restore_directory_contents(MANAGED_DATA_DIR, managed_backup)
            _clear_runtime_caches(clear_db=True)
            _restore_directory_contents(CHROMA_DIR, chroma_backup)
            raise


def _build_vector_index(chroma_dir: str, manifest: dict) -> None:
    settings = get_settings()
    if settings.index_build_mode == "manifest-only":
        from backend.services.rag_service import _build_db_meta, _get_pdf_files

        if os.path.exists(chroma_dir):
            shutil.rmtree(chroma_dir)
        os.makedirs(chroma_dir, exist_ok=True)
        with open(os.path.join(chroma_dir, "integration-index.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        with open(os.path.join(chroma_dir, "db_meta.json"), "w", encoding="utf-8") as handle:
            json.dump(_build_db_meta(_get_pdf_files()), handle, ensure_ascii=False, indent=2)
        return

    if settings.index_build_mode != "chroma":
        raise RuntimeError(f"不支援的 INDEX_BUILD_MODE: {settings.index_build_mode}")

    from backend.services.rag_service import init_vector_db

    init_vector_db(force_rebuild=True, persist_directory=chroma_dir)
