import hashlib
import os
import re
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.config import get_settings
from backend.models import Document, DocumentVersion, IndexJob
from backend.storage import get_storage


PDF_HEADER = b"%PDF-"
ALLOWED_VERSION_RE = re.compile(r"^[\w.\-() ]{1,80}$", re.UNICODE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_pdf(filename: str, content_type: str | None, content: bytes) -> tuple[str, int]:
    settings = get_settings()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只允許上傳 PDF 檔案")
    if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="檔案 MIME 類型不是 PDF")
    if not content.startswith(PDF_HEADER):
        raise HTTPException(status_code=400, detail="檔案內容不是有效的 PDF")
    if not content or len(content) > settings.max_pdf_size_bytes:
        max_mb = settings.max_pdf_size_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"PDF 不可超過 {max_mb} MB")
    return hashlib.sha256(content).hexdigest(), len(content)


def validate_version_number(version_number: str) -> str:
    cleaned = version_number.strip()
    if not ALLOWED_VERSION_RE.fullmatch(cleaned):
        raise HTTPException(status_code=400, detail="版本號格式不正確")
    return cleaned


def create_document_with_version(
    session: Session,
    *,
    title: str,
    version_number: str,
    effective_date: date | None,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> Document:
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="文件標題不可為空")
    version_number = validate_version_number(version_number)
    checksum, size_bytes = validate_pdf(filename, content_type, content)
    source_alias = os.path.basename(filename)[:255]
    if session.scalar(select(Document.id).where(Document.source_alias == source_alias).limit(1)):
        stem, extension = os.path.splitext(source_alias)
        source_alias = f"{stem[:210]}-{uuid.uuid4().hex[:12]}{extension or '.pdf'}"
    document = Document(title=title, source_alias=source_alias)
    session.add(document)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="文件標題已存在") from exc
    version = _attach_version(
        session,
        document=document,
        version_number=version_number,
        effective_date=effective_date,
        filename=filename,
        content=content,
        checksum=checksum,
        size_bytes=size_bytes,
    )
    _commit_or_conflict(session, cleanup_object_key=version.object_key)
    return get_document(session, document.id)


def add_document_version(
    session: Session,
    *,
    document_id: str,
    version_number: str,
    effective_date: date | None,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="找不到文件")
    version_number = validate_version_number(version_number)
    checksum, size_bytes = validate_pdf(filename, content_type, content)
    version = _attach_version(
        session,
        document=document,
        version_number=version_number,
        effective_date=effective_date,
        filename=filename,
        content=content,
        checksum=checksum,
        size_bytes=size_bytes,
    )
    _commit_or_conflict(session, cleanup_object_key=version.object_key)
    return get_document(session, document.id)


def _attach_version(
    session: Session,
    *,
    document: Document,
    version_number: str,
    effective_date: date | None,
    filename: str,
    content: bytes,
    checksum: str,
    size_bytes: int,
) -> DocumentVersion:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._") or "document.pdf"
    object_key = f"documents/{document.id}/{uuid.uuid4()}-{safe_name}"
    storage = get_storage()
    storage.upload_pdf(object_key, content)
    version = DocumentVersion(
        document=document,
        title=document.title,
        version_number=version_number,
        effective_date=effective_date,
        original_filename=filename[:255],
        object_key=object_key,
        checksum=checksum,
        size_bytes=size_bytes,
        status="draft",
    )
    document.updated_at = _utcnow()
    session.add(version)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        try:
            storage.delete_file(object_key)
        except Exception:
            pass
        raise HTTPException(status_code=409, detail="版本號或 PDF 內容已存在") from exc
    except Exception:
        session.rollback()
        try:
            storage.delete_file(object_key)
        except Exception:
            pass
        raise
    return version


def _delete_uploaded_object(object_key: str) -> None:
    try:
        get_storage().delete_file(object_key)
    except Exception as exc:
        print(f"⚠️ 無法清理孤兒物件 {object_key}: {exc}")


def _commit_or_conflict(session: Session, cleanup_object_key: str | None = None) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if cleanup_object_key:
            _delete_uploaded_object(cleanup_object_key)
        raise HTTPException(status_code=409, detail="標題、版本號或 PDF 內容已存在") from exc
    except Exception:
        session.rollback()
        if cleanup_object_key:
            _delete_uploaded_object(cleanup_object_key)
        raise


def enqueue_index_job(session: Session, trigger: str, coalesce_pending: bool = True) -> IndexJob:
    if coalesce_pending:
        pending = session.scalar(
            select(IndexJob)
            .where(IndexJob.status == "pending")
            .order_by(IndexJob.created_at)
            .limit(1)
        )
        if pending is not None:
            return pending
    job = IndexJob(trigger=trigger[:30], status="pending")
    session.add(job)
    return job


def list_documents(session: Session) -> list[Document]:
    query = (
        select(Document)
        .options(selectinload(Document.versions))
        .order_by(Document.updated_at.desc())
    )
    return list(session.scalars(query).unique())


def get_document(session: Session, document_id: str) -> Document:
    query = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.versions))
    )
    document = session.scalars(query).unique().one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="找不到文件")
    return document


def publish_version(
    session: Session,
    version_id: str,
    trigger: str = "publish",
    allowed_statuses: set[str] | None = None,
    enqueue_job: bool = True,
) -> IndexJob | None:
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="找不到文件版本")
    if version.status == "published":
        raise HTTPException(status_code=409, detail="此版本已經發布")
    if allowed_statuses is not None and version.status not in allowed_statuses:
        raise HTTPException(status_code=409, detail="版本狀態不符合此操作")

    now = _utcnow()
    siblings = session.scalars(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.status == "published",
        )
        .with_for_update()
    )
    for sibling in siblings:
        sibling.status = "archived"
        sibling.archived_at = now
    session.flush()

    version.status = "published"
    version.published_at = now
    version.archived_at = None
    job = enqueue_index_job(session, trigger) if enqueue_job else None
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="同一份文件只能有一個發布版本") from exc
    return job


def archive_version(session: Session, version_id: str) -> IndexJob:
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="找不到文件版本")
    if version.status != "published":
        raise HTTPException(status_code=409, detail="只有目前發布版本可以停用")
    version.status = "archived"
    version.archived_at = _utcnow()
    job = enqueue_index_job(session, "archive")
    session.commit()
    return job


def delete_draft_version(session: Session, version_id: str) -> None:
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="找不到文件版本")
    if version.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿版本可以刪除")
    try:
        get_storage().delete_file(version.object_key)
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail="物件儲存暫時無法刪除草稿，資料庫內容已保留，可稍後重試",
        ) from exc
    document_id = version.document_id
    remaining = list(
        session.scalars(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.id != version_id,
            )
        )
    )
    if not remaining:
        document = session.get(Document, document_id)
        if document is not None:
            session.delete(document)
    else:
        session.delete(version)
    session.commit()


def get_index_job(session: Session, job_id: str) -> IndexJob:
    job = session.get(IndexJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到索引工作")
    return job


def get_latest_index_job(session: Session) -> IndexJob | None:
    return session.scalar(select(IndexJob).order_by(IndexJob.created_at.desc()).limit(1))


def retry_failed_index_job(session: Session, job_id: str) -> IndexJob:
    failed_job = get_index_job(session, job_id)
    if failed_job.status != "failed":
        raise HTTPException(status_code=409, detail="只有失敗的索引工作可以重試")
    job = enqueue_index_job(session, "retry", coalesce_pending=False)
    session.commit()
    return job
