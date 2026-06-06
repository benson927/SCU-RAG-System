import asyncio
import json
import logging
import threading
import time
from typing import List

import anyio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.security import enforce_rag_rate_limit
from backend.services.rag_service import get_full_system_status, query_rag, query_rag_stream


router = APIRouter()
logger = logging.getLogger(__name__)
_semaphore_lock = threading.Lock()
_rag_semaphore = None
_rag_semaphore_size = None


class RAGQueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="要向知識庫查詢的問題或關鍵字",
    )
    api_key: str | None = Field(default=None, max_length=512, description="Gemini API Key (選填)")
    disable_expansion: bool = Field(default=True, description="是否停用語意擴充加速")
    force_local: bool = Field(default=False, description="是否強制純地端模式")


class RAGQueryResponse(BaseModel):
    answer: str = Field(..., description="RAG 系統產生的回答")
    sources: List[str] = Field(default_factory=list, description="參考的資料來源")


def _get_rag_semaphore() -> threading.BoundedSemaphore:
    global _rag_semaphore, _rag_semaphore_size
    size = max(1, get_settings().rag_max_concurrency)
    with _semaphore_lock:
        if _rag_semaphore is None or _rag_semaphore_size != size:
            _rag_semaphore = threading.BoundedSemaphore(size)
            _rag_semaphore_size = size
    return _rag_semaphore


def _prepare_request(request: RAGQueryRequest) -> tuple[str, str | None]:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="問題內容不可為空。")
    if len(query) > get_settings().max_query_length:
        raise HTTPException(status_code=422, detail="問題內容過長。")
    api_key = None if request.force_local else (request.api_key or "").strip() or None
    return query, api_key


def _acquire_rag_slot() -> threading.BoundedSemaphore:
    semaphore = _get_rag_semaphore()
    if not semaphore.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="目前推論工作已滿，請稍後再試。")
    return semaphore


def _run_query_with_slot(
    semaphore: threading.BoundedSemaphore,
    query: str,
    api_key: str | None,
    disable_expansion: bool,
):
    try:
        return query_rag(query, api_key=api_key, disable_expansion=disable_expansion)
    finally:
        semaphore.release()


@router.post(
    "/rag",
    response_model=RAGQueryResponse,
    dependencies=[Depends(enforce_rag_rate_limit)],
)
async def handle_rag_query(request: RAGQueryRequest):
    query, api_key = _prepare_request(request)
    semaphore = _acquire_rag_slot()
    started_at = time.monotonic()
    try:
        result = await asyncio.wait_for(
            anyio.to_thread.run_sync(
                _run_query_with_slot,
                semaphore,
                query,
                api_key,
                request.disable_expansion,
                abandon_on_cancel=True,
            ),
            timeout=get_settings().rag_timeout_seconds,
        )
        return RAGQueryResponse(answer=result["answer"], sources=result["sources"])
    except TimeoutError:
        logger.warning(
            "RAG request timed out",
            extra={"duration_ms": int((time.monotonic() - started_at) * 1000)},
        )
        raise HTTPException(status_code=504, detail="RAG 推論逾時，請縮短問題或稍後再試。")
    except HTTPException:
        raise
    except Exception:
        logger.exception("RAG request failed")
        raise HTTPException(status_code=500, detail="RAG 推論失敗，請稍後再試。")


@router.post("/rag/stream", dependencies=[Depends(enforce_rag_rate_limit)])
async def handle_rag_query_stream(request: RAGQueryRequest):
    query, api_key = _prepare_request(request)
    semaphore = _acquire_rag_slot()

    def event_generator():
        started_at = time.monotonic()
        try:
            generator = query_rag_stream(
                query,
                api_key=api_key,
                disable_expansion=request.disable_expansion,
            )
            for chunk in generator:
                if time.monotonic() - started_at > get_settings().rag_timeout_seconds:
                    timeout_event = {
                        "type": "error",
                        "content": "RAG 推論逾時，請縮短問題或稍後再試。",
                    }
                    yield f"data: {json.dumps(timeout_event, ensure_ascii=False)}\n\n"
                    return
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception("Streaming RAG request failed")
            error_event = {"type": "error", "content": "RAG 推論失敗，請稍後再試。"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        finally:
            semaphore.release()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status")
async def get_system_status():
    try:
        return get_full_system_status()
    except Exception:
        logger.exception("System status request failed")
        raise HTTPException(status_code=500, detail="無法取得系統狀態。")
