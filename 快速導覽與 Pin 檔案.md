# 📌 RAG 系統核心檔案快速導覽

本文件整理自 [rag_system_guide.md](file:///Users/bensonhong/.gemini/antigravity-ide/brain/2e8e5523-a815-4301-a6c1-71bca01aed16/rag_system_guide.md)，您可以將此文件 Pin 在側邊欄中，即可隨時透過點擊下方連結快速開啟相關檔案。

## 🚀 核心後端服務 (Backend)
* ⚙️ **[backend/main.py](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/backend/main.py)** - FastAPI 伺服器主入口，處理環境變數與路由掛載。
* 🌐 **[backend/api/router.py](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/backend/api/router.py)** - API 路由層，定義 `/api/rag` 與 `/api/rag/stream` 端點。
* 🧠 **[backend/services/rag_service.py](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/backend/services/rag_service.py)** - RAG 核心服務，包含檢索、排序融合及 LLM 推理邏輯。
* 📝 **[backend/services/title_mapping.json](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/backend/services/title_mapping.json)** - PDF 檔名與中文名稱的映射表。

## 💻 核心前端服務 (Frontend)
* 🎨 **[frontend/src/App.jsx](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/frontend/src/App.jsx)** - React + Vite 前端對話介面。

## 🦉 傳統/備用服務
* 📄 **[app.py](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/app.py)** - Streamlit 單頁測試介面。

## 📂 數據與知識庫 (Data & Database)
* 📁 **[data/](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/data)** - 原始法規 PDF 目錄。
* 🗃️ **[chroma_db/](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/chroma_db)** - Vector DB Chroma 向量資料庫儲存目錄。

## ⚙️ FAQ 訓練與自動化生成
* 🛠️ **[scratch/generate_faq_dataset.py](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/scratch/generate_faq_dataset.py)** - 自動化 FAQ 訓練與數據生成核心腳本（增量訓練）。
* 📦 **[data/faq_cache.json](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/data/faq_cache.json)** - 自動化訓練成果快取檔（儲存口語問答對）。

## 📊 評估與測試驗證
* 🧪 **[scratch/run_faq_evaluation.py](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/scratch/run_faq_evaluation.py)** - 100 題自動化評估與回歸測試腳本。
* 📝 **[demo_faq_100.json](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/demo_faq_100.json)** - 100 題評估成果 JSON 數據。
* 📄 **[demo_faq_100.md](file:///Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)/demo_faq_100.md)** - 100 題評估成果 Markdown 報告。
