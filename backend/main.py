from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.router import router as rag_router

app = FastAPI(
    title="完全地端企業知識庫 RAG 系統 API",
    description="基於本地端 PDF 知識庫與 Ollama 推論之 FastAPI RAG 核心後端服務。",
    version="1.0.0"
)

# 配置 CORS，支援 React 前端連線
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地測試允許所有來源，生產環境應限制具體 Port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊 RAG 路由端點
app.include_router(rag_router, prefix="/api", tags=["RAG"])

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "FastAPI RAG 後端伺服器運行中。請訪問 http://localhost:8000/docs 查看 API 文檔。"
    }
