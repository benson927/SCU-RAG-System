import React, { useState, useEffect, useRef } from "react";
import "./App.css";

function App() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "您好！我是您的地端企業知識庫助手。請將 PDF 檔案放入專案根目錄的 `data/` 資料夾，即可開始向我詢問其中的內容。我會嚴格基於文件原文回答您，並提供來源出處。",
      sources: []
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState("checking"); // checking, online, offline
  const chatEndRef = useRef(null);

  // 檢查後端 FastAPI 服務狀態
  const checkStatus = async () => {
    try {
      const res = await fetch("http://localhost:8000/");
      if (res.ok) {
        setBackendStatus("online");
      } else {
        setBackendStatus("offline");
      }
    } catch (e) {
      setBackendStatus("offline");
    }
  };

  useEffect(() => {
    checkStatus();
    // 每 10 秒自動檢查一次連線狀態
    const interval = setInterval(checkStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  // 自動捲動到最新訊息
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userQuery = input.trim();
    setInput("");
    
    // 新增使用者訊息
    setMessages(prev => [...prev, { role: "user", content: userQuery }]);
    setIsLoading(true);

    try {
      const response = await fetch("http://localhost:8000/api/rag", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: userQuery }),
      });

      if (!response.ok) {
        throw new Error("後端 API 回應錯誤");
      }

      const data = await response.json();
      
      // 新增 AI 回答
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.answer,
        sources: data.sources || []
      }]);
    } catch (error) {
      console.error(error);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "❌ 系統推論出錯。請確認：\n1. 後端 FastAPI 服務是否已啟動。\n2. 本地 Ollama 是否運行，且已拉取 `gemma3` 與 `nomic-embed-text` 模型。\n3. `data/` 資料夾下是否有放 PDF 檔案並成功解析。",
        sources: []
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([
      {
        role: "assistant",
        content: "對話歷史已清除。請問有什麼我可以協助您的？",
        sources: []
      }
    ]);
  };

  return (
    <div className="app-container">
      {/* 霓虹動態背景光球 */}
      <div className="aurora-bg">
        <div className="blob blob-purple"></div>
        <div className="blob blob-pink"></div>
        <div className="blob blob-blue"></div>
      </div>

      {/* 頂部導航欄 */}
      <header className="app-header">
        <div className="header-left">
          <span className="logo-emoji">🎓</span>
          <h1>SCU Local <span className="highlight">RAG</span></h1>
          <span className="subtitle">企業內部知識庫</span>
        </div>
        <div className="header-right">
          <div className={`status-badge ${backendStatus}`}>
            <span className="dot"></span>
            {backendStatus === "checking" && "檢測狀態中..."}
            {backendStatus === "online" && "地端伺服器：在線"}
            {backendStatus === "offline" && "地端伺服器：離線"}
          </div>
          {backendStatus === "offline" && (
            <button className="retry-btn" onClick={checkStatus}>
              🔄 重試連線
            </button>
          )}
        </div>
      </header>

      {/* 主體佈局 */}
      <div className="main-layout">
        {/* 左側面板 - 說明與指南 */}
        <aside className="sidebar">
          <div className="sidebar-card">
            <h3>⚙️ 系統運行說明</h3>
            <p>本 RAG 系統完全在您的**本機端**執行，保護企業資料隱私不外洩。</p>
            <div className="step-list">
              <div className="step-item">
                <span className="step-num">1</span>
                <div>
                  <strong>置放文件</strong>
                  <span>將 PDF 放置於 <code>data/</code> 資料夾</span>
                </div>
              </div>
              <div className="step-item">
                <span className="step-num">2</span>
                <div>
                  <strong>執行 Ollama</strong>
                  <span>確認已 Pull <code>gemma3</code> 與 <code>nomic-embed-text</code></span>
                </div>
              </div>
              <div className="step-item">
                <span className="step-num">3</span>
                <div>
                  <strong>後端啟動</strong>
                  <span>於 <code>backend/</code> 運行 FastAPI</span>
                </div>
              </div>
            </div>
          </div>

          <div className="sidebar-card info-card">
            <h3>⚠️ 嚴謹度提示</h3>
            <p>AI 回答時，將**僅依據**您所提供的 PDF 上下文。若無相關資訊，系統會主動回報查無解答，避免模型產生胡言亂語的「幻覺」。</p>
          </div>

          <button className="clear-history-btn" onClick={clearChat}>
            🗑️ 清除對話紀錄
          </button>
        </aside>

        {/* 右側聊天室 */}
        <main className="chat-container">
          <div className="chat-messages">
            {messages.map((msg, index) => (
              <div key={index} className={`message-wrapper ${msg.role}`}>
                <div className="avatar">
                  {msg.role === "user" ? "👤" : "🤖"}
                </div>
                <div className="message-bubble">
                  <div className="message-content">
                    {msg.content.split("\n").map((line, i) => (
                      <p key={i}>{line}</p>
                    ))}
                  </div>
                  
                  {/* 來源卡片 */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="sources-section">
                      <div className="sources-title">📌 參考文獻出處：</div>
                      <div className="sources-list">
                        {msg.sources.map((src, sIdx) => (
                          <span key={sIdx} className="source-tag">
                            📄 {src}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* 思考中載入動畫 */}
            {isLoading && (
              <div className="message-wrapper assistant loading">
                <div className="avatar">🤖</div>
                <div className="message-bubble">
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span className="loading-text">地端 AI (gemma3) 正在搜尋與思考中...</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* 輸入框 */}
          <form className="chat-input-area" onSubmit={handleSubmit}>
            <input
              type="text"
              placeholder={
                backendStatus === "online" 
                  ? "請輸入關於法規或文檔的問題... (例如：宿舍退宿的退費標準是什麼？)" 
                  : "請先啟動本地 FastAPI 後端服務以啟用輸入..."
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isLoading || backendStatus !== "online"}
            />
            <button 
              type="submit" 
              disabled={!input.trim() || isLoading || backendStatus !== "online"}
              className="send-btn"
            >
              <span>發送</span>
              <svg viewBox="0 0 24 24" width="16" height="16">
                <path fill="currentColor" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </form>
        </main>
      </div>
    </div>
  );
}

export default App;
