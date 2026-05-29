import streamlit as st
import os
import sys

# 嘗試載入本機 .env 檔案中的環境變數 (避免引入額外依賴套件)
if os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    val = v.strip().strip("'").strip('"')
                    os.environ[k.strip()] = val
    except Exception:
        pass

# 將 backend 路徑加入 sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from backend.services.rag_service import query_rag, query_rag_stream, check_vector_db_status, init_vector_db

# 初始化向量資料庫快取
if "db" not in st.session_state:
    st.session_state.db = None

# ==============================================================================
# Streamlit 網頁介面設計與配置
# ==============================================================================
st.set_page_config(
    page_title="PDF 規範與法規智慧檢索系統",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 載入自定義 Premium CSS 樣式
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@300..700&family=Gaegu:wght@400;700&family=Yusei+Magic&family=Noto+Sans+TC:wght@400;700&family=Outfit:wght@400;600;800&display=swap');

/* 全域字型與背景設定 */
html, body, [class*="css"], .stApp {
    font-family: 'Outfit', 'Fredoka', 'Yusei Magic', 'Noto Sans TC', sans-serif !important;
    color: #2b2b2b !important;
    background-color: #fffef9 !important; /* 柔軟奶油黃白背景 */
}

/* 頂部精美卡片標題 - 莫蘭迪三色漸層野獸派風格 */
.header-card {
    background: linear-gradient(135deg, #fff0f2 0%, #f1f8f5 50%, #ebf3fd 100%) !important;
    border: 3px solid #2b2b2b !important;
    border-radius: 24px !important;
    color: #2b2b2b !important;
    padding: 2.2rem 2.2rem !important;
    margin-bottom: 2rem !important;
    box-shadow: 7px 7px 0px #2b2b2b !important; /* 經典硬陰影 */
    position: relative;
    overflow: hidden;
}

/* 裝飾性手繪斜條紋 */
.header-card::after {
    content: "✏️ SCU RAG Pro";
    position: absolute;
    bottom: 12px;
    right: 18px;
    font-family: 'Gaegu', cursive;
    font-size: 1.5rem;
    color: rgba(43, 43, 43, 0.2);
    transform: rotate(-6deg);
}

.header-badge {
    display: inline-flex;
    align-items: center;
    background: #e0f2fe !important; /* 晴空藍 */
    color: #0369a1 !important;
    border: 2px solid #2b2b2b !important;
    padding: 0.35rem 0.9rem !important;
    border-radius: 9999px !important;
    font-size: 0.8rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.05em !important;
    margin-bottom: 1.2rem !important;
    box-shadow: 2.5px 2.5px 0px #2b2b2b !important;
}

.header-title {
    font-family: 'Outfit', 'Yusei Magic', sans-serif !important;
    font-size: 2.6rem !important;
    font-weight: 800 !important;
    margin: 0 !important;
    color: #2b2b2b !important;
    line-height: 1.25 !important;
}

.highlight-text {
    background-color: #ffeb3b !important; /* 亮黃色背景 */
    border-bottom: 3.5px dashed #f57f17 !important; /* 手繪底線虛線 */
    color: #2b2b2b !important;
    padding: 0 0.4rem !important;
    border-radius: 6px;
}

.header-subtitle {
    font-size: 1.05rem !important;
    color: #495057 !important;
    margin-top: 1.2rem !important;
    font-weight: 400 !important;
    line-height: 1.7 !important;
}

.header-subtitle strong {
    color: #e8590c !important;
    font-weight: 700 !important;
    text-decoration: underline wavy #ff922b; /* 波浪下劃線 */
}

/* 側邊欄樣式微調 - 手繪筆記本質感 */
[data-testid="stSidebar"] {
    background-color: #faf7f2 !important;
    border-right: 3px solid #2b2b2b !important;
}

/* 摺疊面板自定義樣式 */
.streamlit-expanderHeader {
    background-color: #ffffff !important;
    border: 2.5px solid #2b2b2b !important;
    border-radius: 12px !important;
    padding: 0.7rem 1rem !important;
    box-shadow: 3.5px 3.5px 0px #2b2b2b !important;
    margin-bottom: 0.5rem !important;
}

/* 檢索原文 - 漫畫手寫便條紙風格 */
.chunk-card {
    background-color: #fffbeb !important; /* 馬卡龍暖黃便條紙 */
    border: 2.5px solid #2b2b2b !important;
    padding: 1.4rem 1.2rem !important;
    border-radius: 16px !important;
    box-shadow: 4px 4px 0px #2b2b2b !important;
    margin-top: 1.2rem !important;
    margin-bottom: 1.5rem !important;
    position: relative; /* 用於定位裝飾膠帶 */
}

/* 膠帶效果 */
.chunk-card::before {
    content: "";
    position: absolute;
    top: -12px;
    left: 50%;
    transform: translateX(-50%) rotate(-2deg);
    width: 85px;
    height: 22px;
    background-color: rgba(255, 236, 153, 0.7) !important; /* 半透明黃色膠帶 */
    border: 1.5px dashed #b59e24 !important;
    box-shadow: 0px 1px 3px rgba(0,0,0,0.05);
}

.chunk-source {
    font-weight: 700 !important;
    color: #2b2b2b !important;
    font-size: 0.95rem !important;
    margin-bottom: 0.7rem !important;
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
}

.chunk-score {
    background-color: #e6fcf5 !important;
    color: #0ca678 !important;
    font-size: 0.75rem !important;
    padding: 0.2rem 0.6rem !important;
    border: 1.5px solid #2b2b2b !important;
    border-radius: 9999px !important;
    font-weight: 700 !important;
    box-shadow: 1.5px 1.5px 0px #2b2b2b !important;
}

.chunk-content {
    font-size: 0.9rem !important;
    line-height: 1.6 !important;
    color: #495057 !important;
    white-space: pre-wrap !important;
    background-color: #ffffff !important;
    padding: 0.8rem !important;
    border-radius: 8px !important;
    border: 2px solid #2b2b2b !important;
}

/* 覆蓋 Streamlit chat_input 容器與輸入框 */
[data-testid="stChatInput"] {
    border: 3px solid #2b2b2b !important;
    box-shadow: 5px 5px 0px #2b2b2b !important;
    border-radius: 16px !important;
    background-color: #ffffff !important;
    padding: 4px !important;
    transition: all 0.2s ease-in-out !important;
}
[data-testid="stChatInput"]:focus-within {
    transform: translate(-2px, -2px) !important;
    box-shadow: 7px 7px 0px #2b2b2b !important;
}
[data-testid="stChatInput"] textarea {
    font-family: 'Outfit', 'Fredoka', 'Noto Sans TC', sans-serif !important;
    font-size: 1.05rem !important;
    color: #2b2b2b !important;
}

/* 按鈕 Neobrutalism 改造 */
.stButton>button {
    border: 2.5px solid #2b2b2b !important;
    box-shadow: 3.5px 3.5px 0px #2b2b2b !important;
    background-color: #ffe3e3 !important; /* 淺粉紅 */
    border-radius: 12px !important;
    color: #2b2b2b !important;
    font-weight: 700 !important;
    font-family: 'Outfit', 'Noto Sans TC', sans-serif !important;
    transition: all 0.1s ease-in-out !important;
    padding: 0.5rem 1rem !important;
}
.stButton>button:hover {
    transform: translate(-2px, -2px) !important;
    box-shadow: 5.5px 5.5px 0px #2b2b2b !important;
    background-color: #ffc9c9 !important;
}
.stButton>button:active {
    transform: translate(2px, 2px) !important;
    box-shadow: 1.5px 1.5px 0px #2b2b2b !important;
}

/* Chat Message Bubbles Neobrutalism Styling */
[data-testid="stChatMessage"] {
    background-color: #ffffff !important;
    border: 2.5px solid #2b2b2b !important;
    border-radius: 18px !important;
    padding: 1.3rem !important;
    margin-bottom: 1.5rem !important;
    box-shadow: 4px 4px 0px #2b2b2b !important;
    transition: all 0.2s ease-in-out !important;
}

/* 懸停時氣泡微微飄浮，強化手感 */
[data-testid="stChatMessage"]:hover {
    transform: translate(-2px, -2px) !important;
    box-shadow: 6px 6px 0px #2b2b2b !important;
}

/* 用戶氣泡 (data-test-role="user") - 莫蘭迪清爽粉綠 */
[data-testid="stChatMessage"][data-test-role="user"] {
    background-color: #e6f4f1 !important;
}

/* 助理氣泡 (data-test-role="assistant") - 櫻花粉白 */
[data-testid="stChatMessage"][data-test-role="assistant"] {
    background-color: #fff2f2 !important;
}

/* 微調展開面板的外觀，加上手繪虛線邊框 */
.streamlit-expanderHeader {
    border-style: dashed !important;
    border-color: #ff922b !important;
    background-color: #fff9db !important;
}

/* 加大對話框內的字體與行距，讓重點更醒目 */
[data-testid="stChatMessage"] .stMarkdown p {
    font-size: 1.15rem !important;
    line-height: 1.8 !important;
    color: #2b2b2b !important;
}
[data-testid="stChatMessage"] .stMarkdown li {
    font-size: 1.15rem !important;
    line-height: 1.8 !important;
    margin-bottom: 0.5rem !important;
}
[data-testid="stChatMessage"] .stMarkdown strong {
    color: #d9480f !important; /* 橘紅色粗體強調 */
    font-weight: 800 !important;
    background-color: #fff4e6 !important;
    padding: 0 5px !important;
    border-radius: 4px !important;
}
</style>
""", unsafe_allow_html=True)


# 5. 側邊欄配置面版
with st.sidebar:
    st.markdown("### 📚 知識庫狀態")
    db_status = check_vector_db_status()
    status_type = db_status["status"]
    friendly_files = db_status["files"]

    # 載入檔名與真實標題的映射，用於側邊欄美化
    import json
    title_mapping = {}
    mapping_path = os.path.join(os.path.dirname(__file__), 'backend', 'services', 'title_mapping.json')
    if os.path.exists(mapping_path):
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                title_mapping = json.load(f)
        except Exception:
            pass

    if status_type == "ready":
        st.success("🟢 知識庫已就緒")
        if friendly_files:
            with st.expander(f"📁 已載入法規列表 ({len(friendly_files)})", expanded=False):
                for f in friendly_files:
                    friendly_name = title_mapping.get(f, f)
                    st.markdown(f"- 📄 {friendly_name}")
        else:
            st.caption("⚠️ data 資料夾中尚無 PDF 檔案。")
        
        # 載入向量資料庫到 session_state 供後續發問使用
        if st.session_state.db is None:
            st.session_state.db = init_vector_db()
            
    elif status_type == "outdated":
        st.warning("🟡 偵測到新法規文件")
        if friendly_files:
            with st.expander(f"📁 待更新法規列表 ({len(friendly_files)})", expanded=True):
                for f in friendly_files:
                    friendly_name = title_mapping.get(f, f)
                    st.markdown(f"- 📄 {friendly_name}")
        
        if st.button("🔄 立即更新/訓練知識庫", use_container_width=True):
            with st.spinner("🔄 正在重新計算 Embedding 並重建知識庫..."):
                st.session_state.db = init_vector_db(force_rebuild=True)
            st.success("🎉 知識庫更新成功！")
            st.rerun()
            
    else:  # "empty"
        st.error("🔴 知識庫為空")
        st.info("請於 `data/` 資料夾下放入 PDF 法規檔案。")
        st.session_state.db = None
        
    st.markdown("---")
    st.markdown("### ⚙️ 系統配置")
    # 優先從 session_state 讀取，若無則從環境變數自動帶入
    default_key = st.session_state.get("gemini_key", os.environ.get("GEMINI_API_KEY", ""))
    gemini_key = st.text_input(
        "🔑 Gemini API 金鑰 (選填)",
        type="password",
        value=default_key,
        help="填入金鑰即可啟用 Google Gemini 雲端 API 加速模式，免除本地運行的卡頓。未填寫則預設使用地端 Ollama 模式。"
    )
    st.session_state.gemini_key = gemini_key

    # ⚡ 查詢加速模式 toggle
    disable_expansion = st.toggle(
        "⚡ 查詢加速模式",
        value=st.session_state.get("disable_expansion", True),
        help="開啟後將跳過 LLM 查詢擴展，直接檢索與生成答案，大幅提升地端模式下的反應速度（秒級回應）。"
    )
    st.session_state.disable_expansion = disable_expansion

    # 🦉 純地端模式 toggle
    force_local = st.toggle(
        "🦉 純地端模式",
        value=st.session_state.get("force_local", False),
        help="啟用後將忽略 Gemini API 金鑰，完全使用本地運行的 Ollama 與 Gemma3 模型進行推論與生成，確保所有數據均在本地端安全處理。"
    )
    st.session_state.force_local = force_local

    if force_local:
        st.info("🦉 系統配置：純地端 Ollama 模式")
    elif gemini_key:
        st.success("⚡ 系統配置：API 加速模式 (Chroma 依然本機執行)")
    else:
        st.info("🦉 系統配置：純地端 Ollama 模式")

    # 移入清除歷史對話按鈕，Neobrutalism 風格化
    st.markdown("---")
    if st.button("🗑️ 清除歷史對話", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")

    # 將系統說明與使用指南 Pin 在側邊欄，預設展開
    with st.expander("📌 系統說明與使用指南", expanded=True):
        st.markdown("""
        **🎓 企業專屬知識庫 RAG 系統 (Ollama)**
        
        本系統是一個**純本地運作**的地端 RAG 智慧檢索系統，旨在提供無延遲、隱私安全且精準的法規與規範解答。
        
        ---
        
        ### 🌟 系統特色
        1. **地端 LLM 引擎**：
           - 結合 **Ollama** 與 **Gemma 3** 模型，確保對話不需連網，保護機密資料。
           - 搭配 **nomic-embed-text** 模型，針對法規文檔建立精準的 Chroma 向量資料庫。
        2. **嚴格無偏差設計**：
           - **防幻覺機制**：透過嚴謹的 Prompt，限制 LLM 只能根據檢索到的段落進行回答，不編造事實。
           - **出處標註與原文展開**：每筆解答都會列出資料來源檔名及頁碼，並附帶原文對照功能。
        
        ---
        
        ### 🛠️ 啟動與運行指令
        請先開啟終端機，執行以下指令**切換至專案目錄**：
        ```bash
        cd "/Users/bensonhong/Desktop/Antigravity專案/管哩資訊系統期末（Benson組)"
        ```
        
        接著執行啟動指令：
        ```bash
        python3 -m streamlit run app.py
        ```
        """)

# 6. 主頁面 Render
st.markdown("""
<div class="header-card">
    <div class="header-badge">🎒 SCU LOCAL & PRIVACY SECURED ✏️</div>
    <h1 class="header-title">📖 SCU 法規規範 <span class="highlight-text">智慧檢索系統</span> 🎓</h1>
    <p class="header-subtitle">
        基於地端高效檢索 (Chroma DB) 與大語言模型 (Ollama/Gemma3) 技術，精準匹配核心法規。系統將<strong>即時對照原文</strong>並<strong>嚴謹標註法規出處</strong>，兼顧隱私安全與檢索精準度。
    </p>
</div>
""", unsafe_allow_html=True)

# 7. 初始化 Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# 顯示過往的對話紀錄
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="🧑‍🎓" if message["role"] == "user" else "🦉"):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            if "engine_type" in message:
                st.caption(f"推論引擎：{message['engine_type']}")
            if "detailed_sources" in message and message["detailed_sources"]:
                with st.expander("🔍 檢索到的法規參考條文原文"):
                    for s in message["detailed_sources"]:
                        st.markdown(f"""
                        <div class="chunk-card">
                            <div class="chunk-source">
                                <span>📌 {s["title"]}</span>
                            </div>
                            <div class="chunk-content">{s["content"]}</div>
                        </div>
                        """, unsafe_allow_html=True)

# 8. 對話輸入框
if query := st.chat_input("請輸入您想查詢的法規關鍵字或問題... (例如：工讀時薪是多少？)"):
    # 呈現使用者問題
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(query)
    st.session_state.messages.append({"role": "user", "content": query})
    
    # 進行 RAG 檢索與回答生成 (串流模式)
    # 若開啟純地端模式，則將 api_key 設為 None，忽略 Gemini 雲端 API
    if st.session_state.get("force_local", False):
        api_key = None
    else:
        api_key = st.session_state.get("gemini_key", None)
        if not api_key:
            api_key = None
            
    disable_expansion = st.session_state.get("disable_expansion", True)
    
    with st.chat_message("assistant", avatar="🦉"):
        # 建立一個 placeholder 顯示正在檢索的提示，避免一開始氣泡呈現空白
        status_placeholder = st.empty()
        status_placeholder.markdown("🔍 *正在檢索本地知識庫並思考中...*")
        
        # 建立 metadata 儲存區與 wrapper 生成器
        st.session_state.current_stream_meta = {
            "sources": [],
            "detailed_sources": [],
            "engine_type": "地端模式 🦉"
        }
        
        def run_stream():
            try:
                has_content = False
                generator = query_rag_stream(
                    query, 
                    api_key=api_key, 
                    db=st.session_state.db, 
                    disable_expansion=disable_expansion
                )
                for chunk in generator:
                    if chunk["type"] == "metadata":
                        st.session_state.current_stream_meta = {
                            "sources": chunk.get("sources", []),
                            "detailed_sources": chunk.get("detailed_sources", []),
                            "engine_type": chunk.get("engine_type", "地端模式 🦉")
                        }
                    elif chunk["type"] == "content":
                        # 收到第一個生成內容時，清空檢索提示字，使回答平滑地逐字出現
                        if not has_content:
                            status_placeholder.empty()
                            has_content = True
                        yield chunk["content"]
                    elif chunk["type"] == "error":
                        if not has_content:
                            status_placeholder.empty()
                            has_content = True
                        yield f"❌ 錯誤：{chunk['content']}"
            except Exception as e:
                status_placeholder.empty()
                yield f"⚠️ 發生錯誤：{e}"

        # 利用 st.write_stream 進行打字機逐字渲染
        answer = st.write_stream(run_stream())
        
        # 獲取最終的 metadata
        meta = st.session_state.current_stream_meta
        engine = meta.get("engine_type", "地端模式 🦉")
        detailed_sources = meta.get("detailed_sources", [])
        
        st.caption(f"推論引擎：{engine}")
        
        # 顯示原文參考條文
        if detailed_sources:
            with st.expander("🔍 檢索到的法規參考條文原文"):
                for s in detailed_sources:
                    st.markdown(f"""
                    <div class="chunk-card">
                        <div class="chunk-source">
                            <span>📌 {s["title"]}</span>
                        </div>
                        <div class="chunk-content">{s["content"]}</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # 將回答寫入 history
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "engine_type": engine,
                "detailed_sources": detailed_sources
            })
