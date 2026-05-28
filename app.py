import streamlit as st
import os
import sys

# 將 backend 路徑加入 sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from backend.services.rag_service import query_rag

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
    st.markdown("### ⚙️ 系統配置")
    gemini_key = st.text_input(
        "🔑 Gemini API 金鑰 (選填)",
        type="password",
        value=st.session_state.get("gemini_key", ""),
        help="填入金鑰即可啟用 Google Gemini 雲端 API 加速模式，免除本地運行的卡頓。未填寫則預設使用地端 Ollama 模式。"
    )
    st.session_state.gemini_key = gemini_key

    if gemini_key:
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
    
    # 進行 RAG 檢索與回答生成
    api_key = st.session_state.get("gemini_key", None)
    with st.spinner("系統正在檢索與思考中..."):
        try:
            result = query_rag(query, api_key=api_key)
            error_msg = None
        except Exception as e:
            error_msg = f"⚠️ 發生錯誤：{e}"
            result = None
    
    # 開始處理回答
    with st.chat_message("assistant", avatar="🦉"):
        if error_msg:
            st.markdown(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg,
                "detailed_sources": []
            })
        else:
            answer = result["answer"]
            engine = result.get("engine_type", "地端模式 🦉")
            st.markdown(answer)
            st.caption(f"推論引擎：{engine}")
            
            # 顯示原文
            detailed_sources = result.get("detailed_sources", [])
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
