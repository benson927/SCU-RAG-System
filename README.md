# 🎓 SCU 法規規範智慧檢索系統 (管資期末 - Benson組)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Ollama](https://img.shields.io/badge/Ollama-Offline%20LLM-black)](https://ollama.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20DB-orange)](https://www.trychroma.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

本專案是一個為東吳大學法規與規範設計的 **地端安全 + 雲端加速雙模 RAG (Retrieval-Augmented Generation) 智慧檢索系統**。

系統具備**嚴格防幻覺機制**，限制大語言模型只能根據您提供的法規 PDF 檔案內容進行回答，杜絕 AI 瞎編。每次回覆均會**嚴謹標註參考出處與檔名**，並提供**原文對照展開**功能，是兼顧個人隱私與檢索準確度的智慧檢索解決方案。

---

## 🌟 系統特色與亮點

*   🎨 **Neobrutalism (新野獸主義) 視覺設計**：前端介面採用莫蘭迪色系與奶油黃背景，搭配粗邊框、硬陰影與手繪條紋裝飾，打破傳統網頁的呆板感。
*   🔒 **地端安全隱私保障 (Ollama)**：預設使用純地端 `Ollama` + `Gemma 3` 運行，所有法規 PDF 與提問完全不出網，100% 保障資料隱私。
*   ⚡ **雲端 API 雙模切換 (Gemini)**：側邊欄提供填寫 Gemini API 金鑰欄位。填入後可一鍵切換至 Google Gemini 雲端加速模式，免除地端推論時的卡頓，大幅提升回應速度（Chroma 向量庫依然在本地執行）。
*   📚 **自動化向量資料庫建立**：只要將新的 PDF 檔案放進 `data/` 資料夾，RAG 引擎便會在初次運行時自動載入、切片、並將向量存入本地的 `chroma_db/` 資料庫。
*   📋 **出處回溯與防幻覺**：在系統提示詞中施加強烈約束，若檢索資料中沒有答案，系統會禮貌拒答而非捏造事實。回覆下方會顯示手繪風格的「條文原文卡片」供交叉核對。

---

## 🏗️ 系統技術架構

本系統採用經典的 **RAG (檢索增強生成)** 工作流：

```mermaid
graph TD
    A[使用者輸入提問] --> B{是否提供 Gemini API Key?}
    B -- 是 --> C[啟用 Gemini 雲端模型加速]
    B -- 否 --> D[啟用 Ollama 本地 Gemma3 推論]
    
    A --> E[多查詢語意擴充 Query Expansion]
    E --> F[Chroma 本地向量資料庫檢索]
    F --> G[篩選與排序相關法規文本段落]
    
    C & D --> H[將提問與檢索段落放入 RAG 嚴格提示詞範本]
    G --> H
    H --> I[生成回答 + 標註法規出處檔名]
    I --> J[於前端 UI 渲染回答與「法規參考條文原文卡片」]
```

---

## 📂 專案目錄結構

```text
├── app.py                  # Streamlit 網頁主程式 (Neobrutalism UI 設計)
├── requirements.txt         # 系統 Python 套件依賴清單
├── test_rag.py              # RAG 整合端到端測試指令
├── test_retrieval.py        # 檢索引擎與分詞翻譯單元測試指令
│
├── backend/                 # 後端模組資料夾
│   ├── main.py              # 後端 API 主入口
│   ├── requirements.txt     # 後端依賴
│   └── services/
│       ├── rag_service.py   # RAG 核心檢索與生成邏輯 (Chroma + Ollama/Gemini)
│       └── title_mapping.json  # 檔案名稱與法規名稱對照表
│
├── chroma_db/               # 本地向量資料庫目錄 (儲存向量化後的法規數據)
├── data/                    # 原始法規 PDF 存放處 (在此放入 PDF 以自動建檔)
└── frontend/                # React + Vite 前端專案目錄 (備用進階 Web UI)
```

---

## 🛠️ 安裝與開發環境部署

請先開啟您的終端機 (Terminal)，切換至本專案的根目錄：
```bash
cd "/Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)"
```

### 1. 安裝 Python 套件依賴
建議使用 Python 3.10 以上版本，執行以下指令安裝所需套件：
```bash
python3 -m pip install -r requirements.txt
```

### 2. 安裝並運行地端大語言模型 (Ollama 模式)
如果您想使用 100% 本地地端模式，請完成以下步驟：
1. 前往 [Ollama 官方網站](https://ollama.com/) 下載並安裝適用於 Mac 的應用程式。
2. 啟動 Ollama 軟體。
3. 打開終端機，拉取專案所需的嵌入模型與生成模型：
   ```bash
   # 下載向量嵌入模型
   ollama pull nomic-embed-text
   
   # 下載主推論語言模型
   ollama pull gemma3
   ```
4. 確保 Ollama 在背景持續運行 (預設埠口為 `http://localhost:11434`)。

### 3. 配置 Gemini API 金鑰 (雲端加速模式)
如果您嫌地端執行速度較慢，可以前往 [Google AI Studio](https://aistudio.google.com/) 免費申請 Gemini API Key。
* 啟動系統後，在網頁左側的 **「⚙️ 系統配置」** 欄位中直接貼上您的金鑰，系統將自動開啟 API 加速推論！

---

## 🚀 啟動與測試

### 方案一：啟動 Streamlit 視覺化檢索介面
這是最直覺的測試方式，能開啟精美的網頁介面對話：
```bash
python3 -m streamlit run app.py
```
* 執行後，瀏覽器會自動開啟 [http://localhost:8501](http://localhost:8501)。

### 方案二：執行 RAG 整合測試腳本
在終端機中直接模擬 RAG 檢索流程（包含 Ollama 喚醒、向量庫搜尋與模型生成）：
```bash
python3 test_rag.py
```

### 方案三：執行檢索單元測試
測試分詞、Boosting 加權、中英跨語言語意增強是否能正常運作：
```bash
python3 test_retrieval.py
```

---

## 📚 目前已載入之法規資料庫 (置於 `data/` 目錄)

*   東吳大學學生會會費代收辦法
*   東吳大學碩、博士班優秀新生獎勵辦法
*   東吳大學學生獎懲委員會組織章程
*   東吳大學學生清寒急難救助金實施辦法
*   東吳大學獎助學金申請審核辦法
*   東吳大學學生請假規則 (Soochow University Student Leave Regulations)
*   東吳大學端木愷校長獎學金實施要點
*   東吳大學學生銷過實施辦法
*   東吳大學學生社團組織及活動辦法
*   東吳大學校外學生宿舍輔導及管理辦法
*   東吳大學學生工讀助學實施辦法
*   東吳大學優秀應屆畢業生選拔及獎勵辦法
*   東吳大學研究生獎助學金辦法
*   東吳大學優良導師獎勵辦法
