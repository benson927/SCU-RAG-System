import os

# 嘗試載入本機 .env 檔案中的環境變數 (避免引入額外依賴套件)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CURRENT_DIR)
_env_path = os.path.join(_PROJECT_ROOT, ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    val = v.strip().strip("'").strip('"')
                    os.environ[k.strip()] = val
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.router import router as rag_router

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

app = FastAPI(
    title="完全地端企業知識庫 RAG 系統 API",
    description="基於本地端 PDF 知識庫與 Ollama 推論之 FastAPI RAG 核心後端服務。",
    version="1.0.0"
)

# 配置 CORS，支援 React 前端連線
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
