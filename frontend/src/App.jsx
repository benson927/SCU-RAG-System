import { useState, useEffect, useRef } from "react";
import "./App.css";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

// 輕量手繪風 Markdown 解析器 (零套件依賴，實現螢光筆劃重點)
const renderMarkdown = (text) => {
  if (!text) return "";
  
  // 1. 安全逸出 HTML 特殊字元
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
    
  // 2. 粗體替換為手繪螢光筆 strong 標記
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="manga-highlight">$1</strong>');
  
  // 3. 按行處理列表與段落
  const lines = html.split("\n");
  const processedLines = lines.map(line => {
    const trimmed = line.trim();
    if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
      const content = trimmed.substring(2);
      return `<li class="manga-li">${content}</li>`;
    }
    return `<p class="manga-p">${line}</p>`;
  });
  
  return processedLines.join("");
};

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
  const [showLaws, setShowLaws] = useState(false);
  const [showPDFModal, setShowPDFModal] = useState(false); // 新增 PDF 彈窗狀態控制
  const [slideIndex, setSlideIndex] = useState(0); // 新增當前投影片索引狀態
  const [showConfig, setShowConfig] = useState(false); // 新增系統配置面板折疊狀態
  const [geminiKey, setGeminiKey] = useState(localStorage.getItem("geminiKey") || "");
  const [disableExpansion, setDisableExpansion] = useState(localStorage.getItem("disableExpansion") !== "false"); // 預設為 true
  const [forceLocal, setForceLocal] = useState(localStorage.getItem("forceLocal") === "true"); // 預設為 false
  const [dbStatus, setDbStatus] = useState("empty"); // ready, outdated, empty
  const [pdfCount, setPdfCount] = useState(0);
  const [faqCount, setFaqCount] = useState(0);
  const [ollamaStatus, setOllamaStatus] = useState("offline"); // online, offline
  const [loadedFiles, setLoadedFiles] = useState([]);
  const chatEndRef = useRef(null);
  const ragAbortRef = useRef(null);
  const statusCheckRef = useRef(null);
  const isCloudMode = !forceLocal && geminiKey.trim();
  const activeEngineName = isCloudMode ? "Gemini 2.5 Flash" : "Gemma 3 (Ollama)";

  // 簡報鍵盤事件監聽 (左右方向鍵換頁，Esc 關閉)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!showPDFModal) return;
      if (e.key === "ArrowLeft") {
        setSlideIndex(prev => Math.max(0, prev - 1));
      } else if (e.key === "ArrowRight") {
        setSlideIndex(prev => Math.min(8, prev + 1));
      } else if (e.key === "Escape") {
        setShowPDFModal(false);
        setSlideIndex(0);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showPDFModal]);

  // 檢查後端 FastAPI 服務狀態與系統健康度
  const checkStatus = async () => {
    if (statusCheckRef.current) return;
    const abortController = new AbortController();
    statusCheckRef.current = abortController;
    try {
      const res = await fetch(`${API_BASE_URL}/api/status`, {
        signal: abortController.signal,
      });
      if (res.ok) {
        const data = await res.json();
        setBackendStatus("online");
        setDbStatus(data.db_status || "empty");
        setPdfCount(data.pdf_count || 0);
        setFaqCount(data.faq_count || 0);
        setOllamaStatus(data.ollama_status || "offline");
        setLoadedFiles(data.loaded_files || []);
      } else {
        setBackendStatus("offline");
        setOllamaStatus("offline");
      }
    } catch (error) {
      if (error?.name === "AbortError") return;
      setBackendStatus("offline");
      setOllamaStatus("offline");
    } finally {
      if (statusCheckRef.current === abortController) {
        statusCheckRef.current = null;
      }
    }
  };

  useEffect(() => {
    const initialCheck = window.setTimeout(() => {
      void checkStatus();
    }, 0);
    const checkWhenVisible = () => {
      if (!document.hidden) {
        void checkStatus();
      }
    };
    // 每 30 秒自動檢查一次連線狀態，降低 demo 時對後端健康檢查的干擾
    const interval = window.setInterval(() => {
      checkWhenVisible();
    }, 30000);
    document.addEventListener("visibilitychange", checkWhenVisible);
    return () => {
      window.clearTimeout(initialCheck);
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", checkWhenVisible);
    };
  }, []);

  useEffect(() => {
    return () => {
      ragAbortRef.current?.abort();
      statusCheckRef.current?.abort();
    };
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
    
    ragAbortRef.current?.abort();
    const abortController = new AbortController();
    ragAbortRef.current = abortController;
    setIsLoading(true);

    // 新增使用者訊息與空的 AI 回答，用來逐步接收串流內容
    setMessages(prev => [...prev, { role: "user", content: userQuery }, {
      role: "assistant",
      content: "",
      sources: []
    }]);

    let pendingFrame = null;

    try {
      const response = await fetch(`${API_BASE_URL}/api/rag/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ 
          query: userQuery,
          api_key: geminiKey,
          disable_expansion: disableExpansion,
          force_local: forceLocal
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error("後端 API 回應錯誤");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let partialChunk = "";
      
      let finalAnswer = "";
      let finalSources = [];

      const flushAssistantMessage = () => {
        pendingFrame = null;
        setMessages(prev => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          updated[lastIdx] = {
            ...updated[lastIdx],
            content: finalAnswer,
            sources: finalSources
          };
          return updated;
        });
      };

      const scheduleAssistantUpdate = () => {
        if (pendingFrame !== null) return;
        pendingFrame = window.requestAnimationFrame(flushAssistantMessage);
      };

      while (true) {
        const { value, done } = await reader.read();
        if (abortController.signal.aborted) break;
        if (done) break;

        const textChunk = decoder.decode(value, { stream: true });
        partialChunk += textChunk;

        // 以 "\n\n" 切分 SSE 事件
        const events = partialChunk.split("\n\n");
        // 保留最後一個可能不完整的片段
        partialChunk = events.pop();

        for (const event of events) {
          if (event.trim().startsWith("data: ")) {
            const dataStr = event.trim().slice(6);
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.type === "metadata") {
                finalSources = parsed.sources || [];
                scheduleAssistantUpdate();
              } else if (parsed.type === "content") {
                finalAnswer += parsed.content;
                scheduleAssistantUpdate();
              } else if (parsed.type === "error") {
                finalAnswer += `\n❌ 錯誤：${parsed.content}`;
                scheduleAssistantUpdate();
              }
            } catch (e) {
              console.error("解析串流資料失敗:", e);
            }
          }
        }
      }

      if (abortController.signal.aborted) {
        if (pendingFrame !== null) {
          window.cancelAnimationFrame(pendingFrame);
        }
        return;
      }

      if (pendingFrame !== null) {
        window.cancelAnimationFrame(pendingFrame);
      }
      flushAssistantMessage();
    } catch (error) {
      if (pendingFrame !== null) {
        window.cancelAnimationFrame(pendingFrame);
      }
      if (error?.name === "AbortError") {
        return;
      }
      console.error(error);
      setMessages(prev => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (updated[lastIdx]?.role === "assistant" && updated[lastIdx]?.content === "") {
          updated[lastIdx] = {
            role: "assistant",
            content: "❌ 系統推論出錯。請確認：\n1. 後端 FastAPI 服務是否已啟動。\n2. 本地 Ollama 是否運行，且已拉取 `gemma3` 與 `nomic-embed-text` 模型。\n3. `data/` 資料夾下是否有放 PDF 檔案並成功解析。",
            sources: []
          };
        } else {
          updated.push({
            role: "assistant",
            content: "❌ 系統推論中斷。連線可能已異常斷開。",
            sources: []
          });
        }
        return updated;
      });
    } finally {
      if (ragAbortRef.current === abortController) {
        ragAbortRef.current = null;
        setIsLoading(false);
      }
    }
  };

  const clearChat = () => {
    ragAbortRef.current?.abort();
    ragAbortRef.current = null;
    setIsLoading(false);
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
          {/* 系統運行說明 */}
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

          {/* 知識庫狀態與法規列表 */}
          <div className="sidebar-card laws-card">
            <div className="laws-header" onClick={() => setShowLaws(!showLaws)}>
              <h3>📚 知識庫狀態</h3>
              <span className={`arrow ${showLaws ? "open" : ""}`}>{showLaws ? "▲" : "▼"}</span>
            </div>
            
            {backendStatus === "offline" ? (
              <div className="db-ready-badge" style={{ color: "#842029", backgroundColor: "#f8d7da" }}>
                <span className="pulse-dot" style={{ backgroundColor: "#ff7675", boxShadow: "0 0 0 0 rgba(255, 118, 117, 0.7)" }}></span>
                <span>後端離線，無法取得狀態</span>
              </div>
            ) : dbStatus === "ready" ? (
              <div className="db-ready-badge" style={{ color: "#0f5132", backgroundColor: "#f0fdf4" }}>
                <span className="pulse-dot" style={{ backgroundColor: "#55efc4", boxShadow: "0 0 0 0 rgba(85, 239, 196, 0.7)" }}></span>
                <span>{pdfCount} 份法規 & {faqCount} 筆 FAQ 已載入</span>
              </div>
            ) : dbStatus === "outdated" ? (
              <div className="db-ready-badge" style={{ color: "#664d03", backgroundColor: "#fff3cd" }}>
                <span className="pulse-dot" style={{ backgroundColor: "#f1c40f", boxShadow: "0 0 0 0 rgba(241, 196, 15, 0.7)" }}></span>
                <span>法規變更，資料庫需要重建</span>
              </div>
            ) : (
              <div className="db-ready-badge" style={{ color: "#842029", backgroundColor: "#f8d7da" }}>
                <span className="pulse-dot" style={{ backgroundColor: "#ff7675", boxShadow: "0 0 0 0 rgba(255, 118, 117, 0.7)" }}></span>
                <span>知識庫為空，請放入 PDF 檔案</span>
              </div>
            )}
            
            {showLaws && (
              <ul className="law-list">
                {loadedFiles.length > 0 ? (
                  loadedFiles.map((file, idx) => (
                    <li key={idx}>{file}</li>
                  ))
                ) : (
                  <li style={{ fontStyle: "italic", opacity: 0.6, listStyleType: "none" }}>無已載入法規</li>
                )}
              </ul>
            )}
          </div>

          {/* 🤖 推論引擎配置 (可折疊面板) */}
          <div className="sidebar-card engine-card configurable">
            <div className="engine-header" onClick={() => setShowConfig(!showConfig)}>
              <h3>🤖 推論引擎配置</h3>
              <span className={`arrow ${showConfig ? "open" : ""}`}>{showConfig ? "▲" : "▼"}</span>
            </div>
            
            {/* 運作狀態徽章 */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              <div className="current-engine-badge" style={{ margin: "0.5rem 0 0.8rem 0" }}>
                <span className={`engine-dot ${isCloudMode ? "cloud" : "local"}`}></span>
                <span>
                  {isCloudMode ? "雲端加速模式 ⚡" : "純地端模式 🦉"}
                </span>
              </div>
              
              <div className="current-engine-badge" style={{ margin: "0.5rem 0 0.8rem 0" }}>
                <span className="engine-dot" style={{ backgroundColor: ollamaStatus === "online" ? "#55efc4" : "#ff7675" }}></span>
                <span>
                  Ollama 服務：{ollamaStatus === "online" ? "在線" : "離線"}
                </span>
              </div>
            </div>
            
            {showConfig && (
              <div className="config-form" onClick={(e) => e.stopPropagation()}>
                <div className="config-input-group">
                  <label>🔑 Gemini API 金鑰 (選填)</label>
                  <input 
                    type="password"
                    placeholder="請輸入 API Key 以啟用加速..."
                    value={geminiKey}
                    onChange={(e) => {
                      setGeminiKey(e.target.value);
                      localStorage.setItem("geminiKey", e.target.value);
                    }}
                  />
                </div>
                
                <div className="config-toggle-group">
                  <div className="toggle-item">
                    <div className="toggle-label-desc">
                      <strong>⚡ 查詢加速模式</strong>
                      <span>跳過語意擴充，秒級回應</span>
                    </div>
                    <label className="switch">
                      <input 
                        type="checkbox"
                        checked={disableExpansion}
                        onChange={(e) => {
                          setDisableExpansion(e.target.checked);
                          localStorage.setItem("disableExpansion", e.target.checked);
                        }}
                      />
                      <span className="slider round"></span>
                    </label>
                  </div>
                  
                  <div className="toggle-item">
                    <div className="toggle-label-desc">
                      <strong>🦉 純地端模式</strong>
                      <span>忽略金鑰，完全使用本地模型</span>
                    </div>
                    <label className="switch">
                      <input 
                        type="checkbox"
                        checked={forceLocal}
                        onChange={(e) => {
                          setForceLocal(e.target.checked);
                          localStorage.setItem("forceLocal", e.target.checked);
                        }}
                      />
                      <span className="slider round"></span>
                    </label>
                  </div>
                </div>
              </div>
            )}
            
            {/* 預設小細節 */}
            <div className="engine-info">
              <div className="info-item">
                <span>生成模型</span>
                <strong>{activeEngineName}</strong>
              </div>
              <div className="info-item">
                <span>向量嵌入</span>
                <strong>Nomic-Embed-Text</strong>
              </div>
            </div>
          </div>

          {/* 嚴謹度提示 */}
          <div className="sidebar-card info-card">
            <h3>⚠️ 嚴謹度提示</h3>
            <p>AI 回答時，將**僅依據**您所提供的 PDF 上下文。若無相關資訊，系統會主動回報查無解答，避免模型產生胡言亂語的「幻覺」。</p>
          </div>

          {/* 側邊欄行動按鈕組 */}
          <div className="sidebar-actions">
            <button className="view-presentation-btn" onClick={() => setShowPDFModal(true)}>
              🌐 開啟專案簡報
            </button>
            <button className="clear-history-btn" onClick={clearChat}>
              🗑️ 清除對話紀錄
            </button>
          </div>
        </aside>

        {/* 右側聊天室 */}
        <main className="chat-container">
          <div className="chat-messages">
            {messages.length <= 1 && !isLoading ? (
              <div className="welcome-banner">
                <div className="welcome-content">
                  <span className="welcome-badge">✨ 100% 本地安全檢索 + 拒絕 AI 幻覺</span>
                  <h2>東吳規章 <span className="highlight-text">智慧導航員</span> ✏️</h2>
                  <p className="welcome-desc">
                    我們重新定義了校園法規的檢索體驗。透過<strong>無網本地運作</strong>捍衛隱私，以及<strong>條文原文秒級對照</strong>阻絕幻覺。在這裡，規章不再是冷冰冰的條文，而是有憑有據的即時智慧。
                  </p>
                  <div className="welcome-tips">
                    💡 試試提問這些東吳規章問題：
                    <ul>
                      <li>期末考請假期限是多久？要送去哪裡審核？</li>
                      <li>拿到端木愷校長獎學金後，下學期學業成績平均要幾分才能續領？</li>
                      <li>宿舍輔導或管理人員在未獲得學生同意下，可以隨意進入寢室檢查嗎？</li>
                    </ul>
                  </div>
                </div>
                <div className="welcome-mascot">
                  <img src="/doodle_monster.png" alt="Moomin Mascot" />
                  <span className="mascot-tag">SCU RAG Pro</span>
                </div>
              </div>
            ) : (
              messages.map((msg, index) => (
                <div key={index} className={`message-wrapper ${msg.role}`}>
                  <div className="avatar">
                    {msg.role === "user" ? "👤" : "🤖"}
                  </div>
                  <div className="message-bubble">
                    <div 
                      className="message-content"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                    />
                    
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
              ))
            )}

            {/* 思考中載入動畫 */}
            {isLoading && (messages.length === 0 || messages[messages.length - 1].role !== "assistant" || messages[messages.length - 1].content === "") && (
              <div className="message-wrapper assistant loading">
                <div className="avatar">🤖</div>
                <div className="message-bubble">
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span className="loading-text">{activeEngineName} 正在搜尋與思考中...</span>
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

      {/* 專案簡報 PDF 全螢幕手繪風彈窗 (Modal) */}
      {showPDFModal && (
        <div className="pdf-modal-overlay" onClick={() => { setShowPDFModal(false); setSlideIndex(0); }}>
          <div className="pdf-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="pdf-modal-header">
              <span className="pdf-modal-title">🎓 MIS 期末專案簡報</span>
              <button className="pdf-modal-close" onClick={() => { setShowPDFModal(false); setSlideIndex(0); }}>
                ❌ 關閉簡報
              </button>
            </div>
            <div className="pdf-modal-body">
              <div className="slide-container">
                <img 
                  src={`/slides/slide_${slideIndex + 1}.png`} 
                  alt={`Slide ${slideIndex + 1}`}
                  className="slide-image"
                />
              </div>
              
              {/* 投影片手繪風底部控制列 */}
              <div className="slide-controls">
                <button 
                  className="slide-btn" 
                  onClick={() => setSlideIndex(prev => Math.max(0, prev - 1))}
                  disabled={slideIndex === 0}
                >
                  ◀ 上一頁
                </button>
                <div className="slide-page-info">
                  <span className="slide-page-text">第 {slideIndex + 1} / 9 頁</span>
                  <div className="slide-dots">
                    {Array.from({ length: 9 }).map((_, idx) => (
                      <span 
                        key={idx} 
                        className={`slide-dot ${idx === slideIndex ? "active" : ""}`}
                        onClick={() => setSlideIndex(idx)}
                      />
                    ))}
                  </div>
                </div>
                <button 
                  className="slide-btn" 
                  onClick={() => setSlideIndex(prev => Math.min(8, prev + 1))}
                  disabled={slideIndex === 8}
                >
                  下一頁 ▶
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
