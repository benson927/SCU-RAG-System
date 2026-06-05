# Legacy Demo Data

此目錄保存 SCU Law RAG System 的展示法規與 FAQ 資料。

## 正式文件流程

啟用 `DATABASE_URL` 後，PostgreSQL 是文件 metadata 的唯一主資料來源，PDF
存放於 S3 相容物件儲存。請從 React 文件管理後台上傳、發布、停用或回滾版本。

正式模式只會將目前 `published` 的版本同步到 `data/managed_documents/` 並建立
Chroma 索引。請勿手動修改 managed directory。

## 一次性匯入

根目錄的既有 PDF 可透過下列指令匯入 PostgreSQL 與物件儲存：

```bash
make import-dry-run
make import-publish
```

底層命令為：

```bash
python -m backend.scripts.import_legacy_data --dry-run
python -m backend.scripts.import_legacy_data --publish
```

匯入工具會讀取 PDF、`backend/services/title_mapping.json` 與 checksum；每份文件
建立 `legacy-initial` 已發布版本。工具可重複執行，已匯入內容會自動跳過。

## Legacy 模式

未設定 `DATABASE_URL` 時，後端仍可直接讀取此目錄的 PDF 與 `faq_cache.json`
建立本機展示索引。這是相容舊版的備用流程，不是正式文件管理方式。

此目錄內容的授權與權利說明請參閱根目錄 [NOTICE.md](../NOTICE.md)。
