# Security Policy

## Supported version

目前只維護 `main` 分支的最新版本。

## Reporting a vulnerability

請勿將未修補的漏洞、憑證或可利用細節公開在 GitHub Issue。

請透過 GitHub repository 的 **Security advisories > Report a vulnerability** 私下回報，並提供：

- 受影響版本或 commit
- 重現步驟
- 可能影響
- 建議修正方式（如有）

維護者確認後會協調修補與公開時程。一般功能錯誤可使用公開 Issue。

## Deployment notes

- 務必更換 `.env.compose.example` 中的開發密碼。
- 正式環境必須設定獨立的 `ADMIN_TOKEN_SECRET`。
- PostgreSQL、MinIO 與 Chroma 不應直接暴露於公網。
- 啟用 `TRUST_PROXY_HEADERS` 前，reverse proxy 必須覆寫而非轉送任意用戶提供的 forwarded headers。
- Gemini API key 預設只應保留在目前瀏覽器分頁。
