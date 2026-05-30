from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List
import json
import os
from backend.services.rag_service import query_rag, query_rag_stream

router = APIRouter()

class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="要向知識庫查詢的問題或關鍵字")
    api_key: str = Field(default=None, description="Gemini API Key (選填)")
    disable_expansion: bool = Field(default=True, description="是否停用語意擴充加速 (預設 True)")
    force_local: bool = Field(default=False, description="是否強制純地端模式 (預設 False)")

class RAGQueryResponse(BaseModel):
    answer: str = Field(..., description="RAG 系統產生的回答")
    sources: List[str] = Field(default=[], description="參考的資料來源（例如 PDF 檔案名稱與頁數）")

@router.post("/rag", response_model=RAGQueryResponse)
async def handle_rag_query(request: RAGQueryRequest):
    try:
        if request.force_local:
            api_key = None
        else:
            api_key = request.api_key
            if not api_key or not api_key.strip():
                api_key = os.environ.get("GEMINI_API_KEY", None)
                if not api_key or not api_key.strip():
                    api_key = None
                
        result = query_rag(
            request.query, 
            api_key=api_key, 
            disable_expansion=request.disable_expansion
        )
        return RAGQueryResponse(
            answer=result["answer"],
            sources=result["sources"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"地端 RAG 推論失敗: {str(e)}")

@router.post("/rag/stream")
async def handle_rag_query_stream(request: RAGQueryRequest):
    def event_generator():
        try:
            if request.force_local:
                api_key = None
            else:
                api_key = request.api_key
                if not api_key or not api_key.strip():
                    api_key = os.environ.get("GEMINI_API_KEY", None)
                    if not api_key or not api_key.strip():
                        api_key = None
                    
            generator = query_rag_stream(
                request.query, 
                api_key=api_key, 
                disable_expansion=request.disable_expansion
            )
            for chunk in generator:
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            err_msg = {"type": "error", "content": f"地端 RAG 推論失敗: {str(e)}"}
            yield f"data: {json.dumps(err_msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
