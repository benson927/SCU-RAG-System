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

## Common failures

- `migration_revision` 不符：先執行 `alembic upgrade head`。
- `bucket_ready: false`：確認 endpoint、credentials、bucket 名稱與 private bucket 權限。
- Job 長時間 `pending`：確認僅有一個 backend worker，並檢查 JSON logs。
- Job `failed`：管理後台會保留錯誤與稽核紀錄；修正外部服務後使用 retry API。
- Ollama offline：確認模型已下載，且容器可連到 `OLLAMA_BASE_URL`。
