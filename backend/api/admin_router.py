from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import create_admin_token, require_admin, verify_admin_password
from backend.config import get_settings
from backend.database import get_session
from backend.services.document_service import (
    add_document_version,
    archive_version,
    create_document_with_version,
    delete_draft_version,
    get_index_job,
    get_latest_index_job,
    list_documents,
    publish_version,
    retry_failed_index_job,
)
from backend.services.index_worker import wake_index_worker


router = APIRouter()


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1)


async def read_pdf_upload(file: UploadFile) -> bytes:
    limit = get_settings().max_pdf_size_bytes
    content = await file.read(limit + 1)
    if len(content) > limit:
        max_mb = limit // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"PDF 不可超過 {max_mb} MB")
    return content


def _iso(value: datetime | date | None):
    return value.isoformat() if value else None


def serialize_job(job):
    if job is None:
        return None
    return {
        "id": job.id,
        "trigger": job.trigger,
        "status": job.status,
        "error_message": job.error_message,
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
    }


def serialize_document(document):
    return {
        "id": document.id,
        "title": document.title,
        "source_alias": document.source_alias,
        "created_at": _iso(document.created_at),
        "updated_at": _iso(document.updated_at),
        "versions": [
            {
                "id": version.id,
                "title": version.title,
                "version_number": version.version_number,
                "effective_date": _iso(version.effective_date),
                "original_filename": version.original_filename,
                "checksum": version.checksum,
                "size_bytes": version.size_bytes,
                "status": version.status,
                "published_at": _iso(version.published_at),
                "archived_at": _iso(version.archived_at),
                "created_at": _iso(version.created_at),
            }
            for version in document.versions
        ],
    }


@router.post("/login")
def login(request: AdminLoginRequest):
    if not verify_admin_password(request.password):
        raise HTTPException(status_code=401, detail="管理密碼錯誤")
    token, expires_at = create_admin_token()
    return {"access_token": token, "token_type": "bearer", "expires_at": expires_at}


@router.get("/documents", dependencies=[Depends(require_admin)])
def get_documents(session: Session = Depends(get_session)):
    return {
        "documents": [serialize_document(document) for document in list_documents(session)],
        "latest_index_job": serialize_job(get_latest_index_job(session)),
    }


@router.post("/documents", dependencies=[Depends(require_admin)])
async def create_document(
    title: str = Form(...),
    version_number: str = Form(...),
    effective_date: date | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    content = await read_pdf_upload(file)
    document = create_document_with_version(
        session,
        title=title,
        version_number=version_number,
        effective_date=effective_date,
        filename=file.filename or "document.pdf",
        content_type=file.content_type,
        content=content,
    )
    return serialize_document(document)


@router.post("/documents/{document_id}/versions", dependencies=[Depends(require_admin)])
async def create_version(
    document_id: str,
    version_number: str = Form(...),
    effective_date: date | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    content = await read_pdf_upload(file)
    document = add_document_version(
        session,
        document_id=document_id,
        version_number=version_number,
        effective_date=effective_date,
        filename=file.filename or "document.pdf",
        content_type=file.content_type,
        content=content,
    )
    return serialize_document(document)


@router.post("/versions/{version_id}/publish", dependencies=[Depends(require_admin)])
def publish(version_id: str, session: Session = Depends(get_session)):
    job = publish_version(session, version_id, trigger="publish", allowed_statuses={"draft"})
    wake_index_worker()
    return serialize_job(job)


@router.post("/versions/{version_id}/rollback", dependencies=[Depends(require_admin)])
def rollback(version_id: str, session: Session = Depends(get_session)):
    job = publish_version(session, version_id, trigger="rollback", allowed_statuses={"archived"})
    wake_index_worker()
    return serialize_job(job)


@router.post("/versions/{version_id}/archive", dependencies=[Depends(require_admin)])
def archive(version_id: str, session: Session = Depends(get_session)):
    job = archive_version(session, version_id)
    wake_index_worker()
    return serialize_job(job)


@router.delete("/versions/{version_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_version(version_id: str, session: Session = Depends(get_session)):
    delete_draft_version(session, version_id)


@router.get("/index-jobs/{job_id}", dependencies=[Depends(require_admin)])
def index_job(job_id: str, session: Session = Depends(get_session)):
    return serialize_job(get_index_job(session, job_id))


@router.post("/index-jobs/{job_id}/retry", dependencies=[Depends(require_admin)])
def retry_index_job(job_id: str, session: Session = Depends(get_session)):
    job = retry_failed_index_job(session, job_id)
    wake_index_worker()
    return serialize_job(job)
