from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List
from backend.services.rag_service import query_rag

router = APIRouter()

class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="要向知識庫查詢的問題或關鍵字")

class RAGQueryResponse(BaseModel):
    answer: str = Field(..., description="RAG 系統產生的回答")
    sources: List[str] = Field(default=[], description="參考的資料來源（例如 PDF 檔案名稱與頁數）")

@router.post("/rag", response_model=RAGQueryResponse)
async def handle_rag_query(request: RAGQueryRequest):
    try:
        result = query_rag(request.query)
        return RAGQueryResponse(
            answer=result["answer"],
            sources=result["sources"]
        )
    except Exception as e:
        # 詳細記錄錯誤，回傳 500
        raise HTTPException(status_code=500, detail=f"地端 RAG 推論失敗: {str(e)}")
