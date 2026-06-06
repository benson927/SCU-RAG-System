# SCU Law RAG System

[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-black)](https://ollama.com/)
[![CI](https://github.com/benson927/SCU-RAG-System/actions/workflows/ci.yml/badge.svg)](https://github.com/benson927/SCU-RAG-System/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/code-MIT-green.svg)](LICENSE)

> A self-hosted reference implementation for retrieving and managing Soochow University regulations with RAG.
>
> 可自行部署的東吳大學法規 RAG 參考實作，整合文件版本管理、物件儲存、向量檢索與本地 LLM。

<p align="center">
  <img src="images/系統頁面.PNG" alt="SCU Law RAG System" width="100%" />
</p>

SCU Law RAG System 使用 React、FastAPI、PostgreSQL、S3 相容物件儲存、Chroma 與 Ollama，提供法規問答與受密碼保護的文件管理後台。管理者可以上傳草稿、發布新版、停用或回滾歷史版本；只有目前發布的 PDF 與對應 FAQ 會進入檢索索引。

本專案是學生開發的非官方開源專案，不代表東吳大學。模型回答僅供參考，正式資訊請以校方最新公告與法規原文為準。

## 核心功能

- **可追溯的 RAG 問答**：混合 Chroma 向量檢索與 BM25，回答附來源文件與頁碼。
- **本地或雲端推論**：預設使用 Ollama 的 Gemma 3；可選擇提供 Gemini API Key。
- **文件版本管理**：PostgreSQL 保存文件、版本、發布狀態與索引工作紀錄。
- **S3 相容儲存**：PDF 放在 MinIO、Cloudflare R2 或其他 S3 相容服務，資料庫只保存 metadata。
- **安全發布流程**：草稿不會被檢索；發布、停用或回滾後由單一 worker 完整重建 Chroma。
- **管理後台**：提供登入、PDF 驗證、版本時間軸、發布、停用、回滾與失敗工作重試。
- **可恢復索引**：重建失敗時保留上一份文件與 Chroma；服務重啟後會接續未完成工作。
- **索引完整性驗證**：managed PDFs 與 Chroma 共用 generation marker，空 volume 或中斷重建會在啟動時自動排程修復。
- **服務防護**：RAG 與管理登入具備輸入限制、逾時、同時推論上限與基礎 rate limiting。
- **外部服務韌性**：PostgreSQL connection pool 與 S3 操作具備可配置 timeout、重試上限及去敏感化健康資訊。

## 架構

```mermaid
flowchart LR
    U["使用者 / 管理者"] --> FE["React + Vite"]
    FE -->|RAG / SSE / Admin API| API["FastAPI"]

    API --> PG[("PostgreSQL<br/>文件與版本")]
    API --> S3[("MinIO / S3<br/>原始 PDF")]
    API --> JOB["單一索引 Worker"]

    JOB --> PG
    JOB --> S3
    JOB --> MANAGED["Managed PDFs"]
    JOB --> CHROMA[("Chroma<br/>向量索引")]

    API --> CHROMA
    API --> OLLAMA["Ollama<br/>Gemma 3 + nomic-embed-text"]
    API -. optional .-> GEMINI["Gemini API"]
```

## Quick Start

### 需求

- Docker Compose 相容環境：OrbStack、Docker Desktop、Colima 或 Podman
- Node.js 20+
- [Ollama](https://ollama.com/)

macOS 推薦 OrbStack；本專案不依賴 Docker Desktop。

### 1. 準備 Ollama 模型

```bash
ollama pull nomic-embed-text
ollama pull gemma3
```

保持 Ollama 在背景運行，預設 API 為 `http://localhost:11434`。

### 2. 啟動 PostgreSQL、MinIO 與 FastAPI

```bash
cp .env.compose.example .env.compose
make compose-up
```

`.env.compose.example` 只適合本機開發。公開部署前必須更換資料庫、MinIO、管理密碼與 token secret。

確認後端狀態：

```bash
make compose-status
```

正常回應會包含 PostgreSQL、storage bucket、migration revision、worker 與最新索引工作的狀態。

### 3. 匯入展示法規

倉庫保留 15 份公開法規作為展示資料。先預覽，再明確發布：

```bash
make import-dry-run
make import-publish
```

匯入工具可重複執行，已存在的 checksum 會自動跳過。發布後等待 `/api/status` 的 `db_status` 變成 `ready`。

### 4. 啟動 React 前端

```bash
cd frontend
npm install
npm run dev
```

開啟 Vite 終端機顯示的網址，通常是 `http://localhost:5173`；若該埠已使用，可能改為 `5174`。

### 服務入口

| 服務 | 網址 |
| --- | --- |
| React 網站 | `http://localhost:5173` 或 Vite 顯示的埠 |
| FastAPI | `http://localhost:8000` |
| Swagger API 文件 | `http://localhost:8000/docs` |
| MinIO Console | `http://localhost:9001` |
| PostgreSQL | `localhost:5432` |

## 文件管理後台

從網站右上角進入「文件管理」，使用 `.env.compose` 的 `ADMIN_PASSWORD` 登入。Bearer token 只保存在瀏覽器 `sessionStorage`。

1. 填寫法規標題、版本號、生效日期並上傳 PDF。
2. 新上傳內容是 `draft`，不會立即進入 RAG。
3. 確認後按「發布」，worker 會同步所有 `published` 文件並重建索引。
4. 等最新索引工作顯示 `succeeded` 後，新內容才可被檢索。
5. 更新文件時，在原文件下新增版本草稿；舊發布版會在新版發布後成為 `archived`。
6. `published` 可停用，`archived` 可回滾，只有 `draft` 可以永久刪除。

上傳限制包含 PDF 副檔名、MIME、檔頭、檔案大小與 SHA-256 checksum 驗證。

## API

### RAG

| Method | Endpoint | 說明 |
| --- | --- | --- |
| `POST` | `/api/rag` | 一次性 RAG 回答 |
| `POST` | `/api/rag/stream` | SSE 串流回答 |
| `GET` | `/api/status` | RAG、PostgreSQL、storage、migration 與 worker 狀態 |
| `GET` | `/health/live` | 程序存活檢查 |
| `GET` | `/health/ready` | PostgreSQL、migration 與 storage readiness |

RAG request：

```json
{
  "query": "學生工讀時薪是多少？",
  "api_key": null,
  "disable_expansion": true,
  "force_local": true
}
```

### Admin

| Method | Endpoint | 說明 |
| --- | --- | --- |
| `POST` | `/api/admin/login` | 驗證管理密碼並取得短期 token |
| `GET` | `/api/admin/documents` | 文件、版本與最新索引工作 |
| `POST` | `/api/admin/documents` | 建立文件與第一個草稿 |
| `POST` | `/api/admin/documents/{id}/versions` | 上傳新版草稿 |
| `POST` | `/api/admin/versions/{id}/publish` | 發布草稿 |
| `POST` | `/api/admin/versions/{id}/archive` | 停用目前版本 |
| `POST` | `/api/admin/versions/{id}/rollback` | 回滾歷史版本 |
| `DELETE` | `/api/admin/versions/{id}` | 刪除草稿 |
| `GET` | `/api/admin/index-jobs/{id}` | 查詢索引工作 |
| `POST` | `/api/admin/index-jobs/{id}/retry` | 建立失敗工作的重試紀錄 |

## 常用指令

```bash
make compose-up          # 建置並啟動後端服務
make compose-status      # 查看系統狀態
make compose-logs        # 追蹤 FastAPI log
make compose-down        # 停止服務，保留 volumes
make import-dry-run      # 預覽 legacy PDF 匯入
make import-publish      # 匯入並發布 legacy PDF
make test                # 後端 unit + 前端 lint/build
make test-integration    # 真實 PostgreSQL/MinIO 整合測試
make test-smoke          # 需要 Ollama 的 live RAG smoke test
make compose-reset       # 刪除所有 Compose 開發資料
```

`make compose-reset` 會永久刪除本機 PostgreSQL、MinIO、Chroma 與 managed document volumes。

正式維運、備份、還原與故障排除請參閱 [Operations Guide](docs/operations.md)。
後端模組責任與依賴方向請參閱 [Backend Architecture](docs/architecture.md)。

Podman 使用者可覆寫 Compose 命令：

```bash
make compose-up COMPOSE="podman compose"
```

若 runtime 不支援 `host.docker.internal`，請在 `.env.compose` 將 `OLLAMA_BASE_URL` 改為相應宿主機名稱，例如 `host.lima.internal` 或 `host.containers.internal`。

## 測試

```bash
make test
```

正式測試集中於 `tests/`：

- `tests/unit/`：認證、PDF 驗證、文件生命週期、legacy importer、RAG 純邏輯與 worker 原子替換。
- `tests/integration/`：真實 PostgreSQL、MinIO、migration、管理 API 與 managed directory。
- `scripts/smoke_rag.py`：需啟動 Ollama 的 live RAG 檢查，不計入 unit test。

分開執行：

```bash
make test-unit
make test-integration
make test-smoke
```

`make test-integration` 會使用隔離的 Compose override，並以 manifest builder 取代 Ollama embedding。

## Benchmark 與維護工具

- [2026 歷史 benchmark 摘要](docs/benchmark-2026.md)
- `scripts/evaluate_rag.py`：重新執行 104 題本機 benchmark，輸出至 ignored 的 `artifacts/`。
- `scripts/generate_faq_dataset.py`：以 Ollama 或 Gemini 增量更新 FAQ cache。
- `scripts/update_presentation.py`：更新簡報 PDF、WebP 投影片與前端 manifest。
- `scripts/convert_presentation.py`：由保留的簡報 PDF 重建 1920×1080 WebP 與 manifest。

```bash
python scripts/evaluate_rag.py --limit 10
python scripts/generate_faq_dataset.py --provider ollama
make presentation-update
```

`make presentation-update` 會讀取非公開來源檔
`presentation/SCU_RAG_Business_Analysis.pptx`，並更新
`frontend/public/SCU_RAG_Business_Analysis.pdf`；若環境有
LibreOffice，會先由 PPTX 刷新 PDF，再產生 WebP 與
`frontend/public/slides/manifest.json`。沒有 LibreOffice 時會使用既有 PDF。
前端頁數、標題與檔名全部由 manifest 決定，不需修改 React。

歷史 benchmark 的 raw JSON/Markdown 不再提交，避免把一次性生成輸出當成 runtime 資料。

## 雲端部署

不使用 Compose 時，依 [.env.example](.env.example) 設定：

- `DATABASE_URL`
- `DATABASE_CONNECT_TIMEOUT_SECONDS`、`DATABASE_POOL_TIMEOUT_SECONDS`
- `DATABASE_POOL_SIZE`、`DATABASE_MAX_OVERFLOW`
- `ADMIN_PASSWORD`、`ADMIN_TOKEN_SECRET`
- `STORAGE_ENDPOINT`、`STORAGE_BUCKET`
- `STORAGE_ACCESS_KEY`、`STORAGE_SECRET_KEY`
- `STORAGE_CONNECT_TIMEOUT_SECONDS`、`STORAGE_READ_TIMEOUT_SECONDS`、`STORAGE_MAX_ATTEMPTS`
- `OLLAMA_BASE_URL`
- `OLLAMA_CHAT_MODEL`、`OLLAMA_EMBEDDING_MODEL`、`OLLAMA_REQUEST_TIMEOUT_SECONDS`
- `MAX_QUERY_LENGTH`、`RAG_TIMEOUT_SECONDS`、`RAG_MAX_CONCURRENCY`
- `RAG_RATE_LIMIT`、`ADMIN_LOGIN_RATE_LIMIT`、`RATE_LIMIT_WINDOW_SECONDS`
- `TRUST_PROXY_HEADERS`：僅在可信任 reverse proxy 會覆寫 forwarded headers 時啟用
- `CORS_ALLOWED_ORIGINS`

啟動前執行 migration：

```bash
alembic upgrade head
```

Neon + Cloudflare R2 範例：

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@NEON_HOST/DATABASE?sslmode=require
STORAGE_ENDPOINT=https://ACCOUNT_ID.r2.cloudflarestorage.com
STORAGE_REGION=auto
STORAGE_BUCKET=YOUR_PRIVATE_BUCKET
STORAGE_ACCESS_KEY=R2_ACCESS_KEY_ID
STORAGE_SECRET_KEY=R2_SECRET_ACCESS_KEY
STORAGE_FORCE_PATH_STYLE=true
```

正式環境應維持 private bucket、啟用 PostgreSQL TLS，並為 Chroma 與 `data/managed_documents` 掛載持久化磁碟。此版本的 worker 設計為單一實例，請勿同時啟動多個索引 worker。

## Demo / Optional

- 未設定 `DATABASE_URL` 時，FastAPI 仍可使用 `data/` 建立本機展示索引；正式文件流程仍以 PostgreSQL 與物件儲存為準。
- Gemini 僅為選用加速方式；`force_local: true` 可強制使用 Ollama。

## License 與資料聲明

原始程式碼採 [MIT License](LICENSE)。

倉庫中的東吳大學法規、校名、簡報、圖片與其他展示資料不因存放於本倉庫而自動適用 MIT License；相關權利仍屬原權利人。詳見 [NOTICE.md](NOTICE.md)。

本專案非東吳大學官方系統。請勿僅依模型回答做出涉及學生權益、行政程序或法律效果的決定。

提交程式碼前請參閱 [CONTRIBUTING.md](CONTRIBUTING.md)；安全問題請依 [SECURITY.md](SECURITY.md) 私下回報。
