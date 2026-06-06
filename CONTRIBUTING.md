# Contributing

感謝協助改善 SCU Law RAG System。請將變更保持聚焦，避免在同一個 pull request 混入無關重構。

## Development checks

```bash
cp .env.compose.example .env.compose
make test
make test-integration
```

需要本機 Ollama 的檢查另行執行：

```bash
make test-smoke
```

## Pull requests

- 說明問題、方案、行為變更與驗證方式。
- API、migration 或環境變數變更必須同步更新 README。
- 新增資料庫 migration，不修改已發布 migration。
- 不提交 `.env`、credentials、Chroma、managed documents 或生成的 benchmark artifacts。
- 使用者可見行為應附測試；大型 UI 變更應附截圖。
- RAG 修改應遵循 [Backend Architecture](docs/architecture.md) 的模組責任，避免把 repository、retrieval 或 model lifecycle 邏輯重新塞回 `rag_service.py`。

## Commit style

建議使用簡短的 Conventional Commit 前綴，例如 `feat:`、`fix:`、`test:`、`docs:`、`chore:`。
