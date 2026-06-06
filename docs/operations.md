# Operations Guide

## Health checks

- `GET /health/live`：程序是否存活。
- `GET /health/ready`：PostgreSQL、Alembic revision、private bucket 與管理驗證設定是否就緒。
- `GET /api/status`：RAG、Ollama、文件、worker 與最新索引工作的詳細狀態。

## Logs

Backend 以 JSON 輸出 request ID、path、status code 與 latency：

```bash
make compose-logs
```

可將客戶端提供的 `X-Request-ID` 對應至後端 log。正式環境建議集中收集 stdout/stderr。
只接受最長 128 字元的英數 request ID 與 `._:-`；其他值會替換為伺服器產生的 UUID，避免污染 log。

公開健康端點只回傳元件狀態，不包含 driver、endpoint 或 credentials 相關例外文字。詳細故障原因僅寫入後端 log；索引 job 的完整錯誤則只透過管理 API 顯示。

## Connection limits

- `DATABASE_CONNECT_TIMEOUT_SECONDS`：建立 PostgreSQL 連線的最長秒數。
- `DATABASE_POOL_TIMEOUT_SECONDS`：等待 pool connection 的最長秒數。
- `DATABASE_POOL_SIZE`、`DATABASE_MAX_OVERFLOW`：單一 backend instance 的連線上限。
- `STORAGE_CONNECT_TIMEOUT_SECONDS`、`STORAGE_READ_TIMEOUT_SECONDS`：S3 連線與讀取 timeout。
- `STORAGE_MAX_ATTEMPTS`：包含第一次請求在內的總嘗試次數。

調整 PostgreSQL pool 時，需同時考量資料庫供應商的 connection limit。正式環境仍以單一 backend/index worker instance 為前提。

## Backup

至少備份 PostgreSQL 與 private object bucket。Chroma 與 managed documents 可由兩者重建，但持久化可縮短復原時間。

PostgreSQL：

```bash
docker compose --env-file .env.compose exec -T postgres \
  pg_dump -U scu_rag -Fc scu_rag > scu-rag.dump
```

MinIO 可使用 `mc mirror` 備份 private bucket：

```bash
mc mirror local/scu-law-documents ./backup/scu-law-documents
```

請將備份加密並定期執行實際還原演練。

## Restore

1. 還原 PostgreSQL。
2. 還原相同 object keys 至 private bucket。
3. 執行 `alembic upgrade head`。
4. 啟動單一 backend instance。
5. 透過發布、停用、回滾或失敗 job retry 建立索引工作。
6. 確認 `/health/ready` 與 `/api/status`。

若 Chroma volume 遺失，worker 會依 PostgreSQL published versions 與物件儲存重建。
worker 也會比對 managed manifest 與 Chroma generation marker；空 volume、缺檔或 generation 不一致都會建立 `startup_rebuild` 工作。

## Common failures

- `migration_revision` 不符：先執行 `alembic upgrade head`。
- `bucket_ready: false`：確認 endpoint、credentials、bucket 名稱與 private bucket 權限。
- Job 長時間 `pending`：確認僅有一個 backend worker，並檢查 JSON logs。
- Job `failed`：管理後台會保留錯誤與稽核紀錄；修正外部服務後使用 retry API。
- Ollama offline：確認模型已下載，且容器可連到 `OLLAMA_BASE_URL`。
