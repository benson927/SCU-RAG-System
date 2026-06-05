# SCU Law RAG Frontend

React 19 + Vite 前端，包含 RAG 問答介面與文件管理後台。
內嵌簡報圖片由 `../scripts/convert_presentation.py` 從保留的 PDF 產生。

完整安裝、後端、資料匯入與部署說明請參閱專案根目錄的
[README.md](../README.md)。

## Development

```bash
npm install
npm run dev
```

前端預設連線 `http://localhost:8000`。如需使用其他 API host：

```bash
VITE_API_BASE_URL=https://api.example.com npm run dev
```

## Checks

```bash
npm run lint
npm run build
```
