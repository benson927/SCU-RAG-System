import { useState, useEffect, useRef } from "react";
import "./App.css";
import AdminPanel from "./AdminPanel";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

const SAMPLE_QUESTIONS = [
  "期末考請假期限是多久？要送去哪裡審核？",
  "拿到端木愷校長獎學金後，下學期學業成績平均要幾分才能續領？",
  "宿舍輔導或管理人員在未獲得學生同意下，可以隨意進入寢室檢查嗎？",
];

const QUESTION_SCOPES = [
  {
    label: "獎助學金與獎勵",
    keywords: ["獎", "獎助學金", "優秀", "端木愷", "研究生", "新生", "畢業生"],
    examples: [
      "端木愷校長獎學金的續領條件是什麼？",
      "研究生獎助學金怎麼分配？",
    ],
  },
  {
    label: "請假與考試假",
    keywords: ["請假", "Leave"],
    examples: [
      "期末考請假期限是多久？",
      "病假最晚要在什麼期限內辦理？",
    ],
  },
  {
    label: "工讀助學",
    keywords: ["工讀"],
    examples: [
      "學生工讀時薪是多少？",
      "申請工讀助學需要符合什麼條件？",
    ],
  },
  {
    label: "住宿與宿舍管理",
    keywords: ["宿舍", "住宿"],
    examples: [
      "宿舍輔導人員可以進入寢室檢查嗎？",
      "校外宿舍管理有哪些規定？",
    ],
  },
  {
    label: "社團、學生會與會費",
    keywords: ["社團", "學生會", "會費"],
    examples: [
      "社團成立需要符合什麼規定？",
      "學生會費如何代收？",
    ],
  },
  {
    label: "獎懲、銷過與申訴",
    keywords: ["獎懲", "銷過", "申訴"],
    examples: [
      "學生銷過需要符合什麼條件？",
      "學生獎懲委員會如何組成？",
    ],
  },
  {
    label: "導師與校園行政規章",
    keywords: ["導師", "甄選委員會", "章程"],
    examples: [
      "優良導師獎勵的評選方式是什麼？",
      "獎助學金甄選委員會如何組成？",
    ],
  },
];

const getVisibleQuestionScopes = (loadedFiles) => {
  if (!loadedFiles?.length) {
    return QUESTION_SCOPES.slice(0, 5);
  }

  const fileText = loadedFiles.join(" ");
  const matched = QUESTION_SCOPES.filter(scope =>
    scope.keywords.some(keyword => fileText.includes(keyword))
  );
  return matched.length ? matched : QUESTION_SCOPES.slice(0, 5);
};

const CHINESE_ENUMERATORS = "一二三四五六七八九十";

const IMPORTANT_TERMS = [
  "不可以",
  "可以",
  "不得",
  "不得隨意",
  "不得隨意進入",
  "必須",
  "未獲得學生同意",
  "未獲同意",
  "學生同意",
  "特殊危急狀況",
  "特殊危急",
  "事後",
  "書面報告",
  "事後書面報告",
  "核定",
  "核准",
  "審核",
  "學系主任",
  "教務處",
  "學生事務處",
  "學生事務長",
  "住宿學生",
  "學生寢室",
  "寢室檢查",
  "個人隱私",
  "公共安全",
  "五個工作日內",
  "五個工作日",
  "一週內",
  "續領",
  "不得續領",
  "無懲處紀錄",
  "懲處紀錄",
  "學業成績平均",
  "全班排名",
  "前10%",
  "前10％",
  "80分（含）以上",
  "80分(含)以上",
  "八十五分以上",
  "85分以上",
];

const IMPORTANT_PATTERNS = [
  /\d+\s*分\s*[（(]含[）)]\s*以上/g,
  /\d+\s*分\s*以上/g,
  /前\s*\d+\s*[%％]\s*[（(]含[）)]?/g,
  /前\s*\d+\s*[%％]/g,
  /第\s*\d+\s*名/g,
  /新臺幣\s*\d+\s*(?:萬)?元/g,
  /\d+\s*(?:萬)?元/g,
  /\d+\s*個工作日內/g,
  /\d+\s*日內/g,
  /\d+\s*週內/g,
];

const highlightImportantTerms = (text) => {
  if (!text) return "";

  const importantTermsPattern = new RegExp(
    IMPORTANT_TERMS
      .slice()
      .sort((a, b) => b.length - a.length)
      .map(term => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("|"),
    "g"
  );

  const segments = text.split(/(\*\*.*?\*\*)/g);
  return segments.map((segment) => {
    if (segment.startsWith("**") && segment.endsWith("**")) return segment;

    const withTerms = segment.replace(importantTermsPattern, (match) => `**${match}**`);
    return IMPORTANT_PATTERNS.reduce((value, pattern) => {
      const parts = value.split(/(\*\*.*?\*\*)/g);
      return parts.map((part) => {
        if (part.startsWith("**") && part.endsWith("**")) return part;
        return part.replace(pattern, (match) => `**${match}**`);
      }).join("");
    }, withTerms);
  }).join("");
};

const normalizeAnswerText = (text) => {
  if (!text) return "";

  return highlightImportantTerms(text)
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => {
      let normalized = line.trim();

      normalized = normalized.replace(
        new RegExp(`([^\\n])\\s+([${CHINESE_ENUMERATORS}]+、)`, "g"),
        "$1\n$2"
      );
      normalized = normalized.replace(
        new RegExp(`(^|\\n)([${CHINESE_ENUMERATORS}]+、)\\s*`, "g"),
        "$1- "
      );
      normalized = normalized.replace(
        /([^：:])\s+(（[一二三四五六七八九十]+）)/g,
        "$1\n$2"
      );
      normalized = normalized.replace(
        /(^|\n)（([一二三四五六七八九十]+)）\s*/g,
        "$1- "
      );
      normalized = normalized.replace(
        /(^|\n)(\d+[.．、])\s*/g,
        "$1- "
      );

      return normalized;
    })
    .join("\n");
};

// 輕量手繪風 Markdown 解析器 (零套件依賴，實現螢光筆劃重點)
const renderMarkdown = (text) => {
  if (!text) return "";

  const escapeHtml = (value) => value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const escapeAttribute = (value) => escapeHtml(value).replace(/"/g, "&quot;");

  const renderInline = (value) => escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code class="manga-code">$1</code>')
    .replace(/\*\*(.*?)\*\*/g, '<strong class="manga-highlight">$1</strong>');

  const blocks = [];
  let paragraphLines = [];
  let listItems = [];
  let skipInternalSourceBlock = false;
  const normalizedText = normalizeAnswerText(text);
  const shouldRenderSuggestedQuestions = /請把問題問得更具體一點，例如：/.test(normalizedText);

  const flushParagraph = () => {
    if (paragraphLines.length === 0) return;
    blocks.push(`<p class="manga-p">${renderInline(paragraphLines.join(" "))}</p>`);
    paragraphLines = [];
  };

  const flushList = () => {
    if (listItems.length === 0) return;
    const items = listItems
      .map((item) => {
        const suggestedQuestionMatch = shouldRenderSuggestedQuestions
          ? item.match(/^\*\*(.+?[？?])\*\*$/)
          : null;

        if (suggestedQuestionMatch) {
          const question = suggestedQuestionMatch[1].trim();
          return [
            '<li class="manga-li suggested-question-item">',
            `<button type="button" class="suggested-question-btn" data-suggested-question="${escapeAttribute(question)}">`,
            renderInline(question),
            '</button>',
            '</li>',
          ].join("");
        }

        return `<li class="manga-li">${renderInline(item)}</li>`;
      })
      .join("");
    blocks.push(`<ul class="manga-list">${items}</ul>`);
    listItems = [];
  };

  normalizedText.split("\n").forEach((line) => {
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      flushList();
      skipInternalSourceBlock = false;
      return;
    }

    if (/^(來源|資料來源|參考文獻|參考文獻出處|可用來源清單)\s*[:：]/.test(trimmed)) {
      flushParagraph();
      flushList();
      skipInternalSourceBlock = true;
      return;
    }

    if (/^-{3,}$/.test(trimmed)) {
      flushParagraph();
      flushList();
      if (skipInternalSourceBlock) {
        skipInternalSourceBlock = false;
        return;
      }
      skipInternalSourceBlock = false;
      blocks.push('<hr class="manga-separator" />');
      return;
    }

    if (skipInternalSourceBlock && /^[-*]\s+/.test(trimmed)) {
      return;
    }

    skipInternalSourceBlock = false;

    const headingMatch = trimmed.match(/^#{2,4}\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push(`<h4 class="manga-heading">${renderInline(headingMatch[1])}</h4>`);
      return;
    }

    if (/^(重點整理|申請資格|辦理流程|注意事項|組成方式|續領條件|回答|結論)[:：]$/.test(trimmed)) {
      flushParagraph();
      flushList();
      blocks.push(`<h4 class="manga-heading">${renderInline(trimmed.replace(/[:：]$/, ""))}</h4>`);
      return;
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      listItems.push(bulletMatch[1]);
      return;
    }

    if (listItems.length > 0) {
      listItems[listItems.length - 1] = `${listItems[listItems.length - 1]} ${trimmed}`;
      return;
    }

    paragraphLines.push(trimmed);
  });

  flushParagraph();
  flushList();

  return blocks.join("");
};

const getFriendlyErrorMessage = (error) => {
  if (error?.name === "AbortError") return "";

  if (error?.message?.includes("HTTP")) {
    return "目前伺服器有收到問題，但回應沒有成功完成。請先確認知識庫狀態為「已載入」，再重新送出一次。";
  }

  return [
    "目前無法完成回答，請先檢查展示環境是否就緒：",
    "- FastAPI 後端服務是否已啟動。",
    "- 知識庫狀態是否顯示已載入 PDF 與 FAQ。",
    "- 若使用純地端模式，請確認 Ollama 已啟動；若使用雲端加速模式，請確認 Gemini API Key 可用。"
  ].join("\n");
};

function App() {
  const [showAdmin, setShowAdmin] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "您好！我是**東吳規章智慧導航員**。您可以詢問已載入法規中的獎助學金、請假、工讀、宿舍、社團、獎懲等問題；我會依據文件原文回答，並在下方標示參考來源。",
      sources: []
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);
  const [backendStatus, setBackendStatus] = useState("checking"); // checking, online, offline
  const [showLaws, setShowLaws] = useState(false);
  const [showScopes, setShowScopes] = useState(false);
  const [showPDFModal, setShowPDFModal] = useState(false); // 新增 PDF 彈窗狀態控制
  const [slideIndex, setSlideIndex] = useState(0); // 新增當前投影片索引狀態
  const [showConfig, setShowConfig] = useState(false); // 新增系統配置面板折疊狀態
  const [geminiKey, setGeminiKey] = useState(localStorage.getItem("geminiKey") || "");
  const [rememberGeminiKey, setRememberGeminiKey] = useState(Boolean(localStorage.getItem("geminiKey")));
  const [disableExpansion, setDisableExpansion] = useState(localStorage.getItem("disableExpansion") !== "false"); // 預設為 true
  const [forceLocal, setForceLocal] = useState(localStorage.getItem("forceLocal") === "true"); // 預設為 false
  const [dbStatus, setDbStatus] = useState("empty"); // ready, outdated, empty
  const [pdfCount, setPdfCount] = useState(0);
  const [faqCount, setFaqCount] = useState(0);
  const [ollamaStatus, setOllamaStatus] = useState("offline"); // online, offline
  const [loadedFiles, setLoadedFiles] = useState([]);
  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const ragAbortRef = useRef(null);
  const statusCheckRef = useRef(null);
  const isCloudMode = !forceLocal && geminiKey.trim();
  const activeEngineName = isCloudMode ? "Gemini 2.5 Flash" : "Gemma 3 (Ollama)";
  const canAskQuestion = backendStatus === "online" && dbStatus !== "empty";
  const visibleQuestionScopes = getVisibleQuestionScopes(loadedFiles);
  const inputHelpText = (() => {
    if (backendStatus !== "online") return "後端尚未連線，請先啟動 FastAPI。";
    if (dbStatus === "empty") return "知識庫尚未載入，請先放入 PDF。";
    if (dbStatus === "outdated") return "偵測到法規變更，首次提問會自動更新索引。";
    return "";
  })();
  const inputPlaceholder = (() => {
    if (backendStatus !== "online") return "請先啟動本地 FastAPI 後端服務以啟用輸入...";
    if (dbStatus === "empty") return "知識庫尚未載入，請先將 PDF 放入 data/ 資料夾...";
    if (dbStatus === "outdated") return "偵測到法規變更，首次提問會先更新知識庫...";
    return "請輸入關於法規或文檔的問題... (例如：宿舍退宿的退費標準是什麼？)";
  })();

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
    setIsCheckingStatus(true);
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
      setIsCheckingStatus(false);
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

  const askQuestion = async (rawQuery) => {
    const userQuery = rawQuery.trim();
    if (!userQuery || isLoading || !canAskQuestion) return;

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
        throw new Error(`HTTP ${response.status}`);
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
                finalAnswer += `\n目前找不到可回答的依據：${parsed.content}`;
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
      const friendlyMessage = getFriendlyErrorMessage(error);
      setMessages(prev => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (updated[lastIdx]?.role === "assistant" && updated[lastIdx]?.content === "") {
          updated[lastIdx] = {
            role: "assistant",
            content: friendlyMessage,
            sources: []
          };
        } else {
          updated.push({
            role: "assistant",
            content: friendlyMessage || "回答中斷，請重新送出一次問題。",
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    await askQuestion(input);
  };

  const clearChat = () => {
    ragAbortRef.current?.abort();
    ragAbortRef.current = null;
    setInput("");
    setIsLoading(false);
    setMessages([
      {
        role: "assistant",
        content: "對話歷史已清除。您可以從左側「可詢問範圍」挑選範例，或直接輸入想查的東吳規章問題。",
        sources: []
      }
    ]);
  };

  const handleSampleQuestion = (question) => {
    if (canAskQuestion && !isLoading) {
      void askQuestion(question);
      return;
    }

    setInput(question);
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  };

  const handleMessageContentClick = (e) => {
    const questionButton = e.target.closest("[data-suggested-question]");
    if (!questionButton) return;
    void askQuestion(questionButton.dataset.suggestedQuestion || "");
  };

  if (showAdmin) {
    return <AdminPanel apiBaseUrl={API_BASE_URL} onClose={() => setShowAdmin(false)} />;
  }

  return (
    <div className="app-container">
      {/* 頂部導航欄 */}
      <header className="app-header">
        <div className="header-left">
          <span className="logo-emoji">🎓</span>
          <h1>SCU Local <span className="highlight">RAG</span></h1>
          <span className="subtitle">校園規章知識庫</span>
        </div>
        <div className="header-right">
          <button className="admin-entry-btn" type="button" onClick={() => setShowAdmin(true)}>
            文件管理
          </button>
          <div className={`status-badge ${backendStatus}`}>
            <span className="dot"></span>
            {backendStatus === "checking" && "檢測狀態中..."}
            {backendStatus === "online" && "地端伺服器：在線"}
            {backendStatus === "offline" && "地端伺服器：離線"}
          </div>
          {backendStatus === "offline" && (
            <button className="retry-btn" onClick={checkStatus} disabled={isCheckingStatus}>
              {isCheckingStatus ? "檢查中..." : "🔄 重試連線"}
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

          {/* 可詢問範圍 */}
          <div className="sidebar-card scope-card">
            <div className="scope-header" onClick={() => setShowScopes(!showScopes)}>
              <h3>🧭 可詢問範圍</h3>
              <span className={`arrow ${showScopes ? "open" : ""}`}>{showScopes ? "▲" : "▼"}</span>
            </div>
            <div className="scope-summary">
              <span className="pulse-dot"></span>
              <span>{visibleQuestionScopes.length} 類主題可詢問</span>
            </div>
            {showScopes && (
              <div className="scope-list">
                {visibleQuestionScopes.map((scope) => (
                  <div className="scope-item" key={scope.label}>
                    <div className="scope-label">{scope.label}</div>
                    <div className="scope-examples">
                      {scope.examples.slice(0, 2).map((question) => (
                        <button
                          key={question}
                          type="button"
                          className="scope-question-btn"
                          onClick={() => handleSampleQuestion(question)}
                        >
                          {question}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
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
                      const nextKey = e.target.value;
                      setGeminiKey(nextKey);
                      if (rememberGeminiKey) {
                        localStorage.setItem("geminiKey", nextKey);
                      }
                    }}
                  />
                </div>
                
                <div className="config-toggle-group">
                  <div className="toggle-item">
                    <div className="toggle-label-desc">
                      <strong>記住金鑰</strong>
                      <span>關閉時只保留到本頁重新整理前</span>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={rememberGeminiKey}
                        onChange={(e) => {
                          const shouldRemember = e.target.checked;
                          setRememberGeminiKey(shouldRemember);
                          if (shouldRemember && geminiKey.trim()) {
                            localStorage.setItem("geminiKey", geminiKey);
                          } else {
                            localStorage.removeItem("geminiKey");
                          }
                        }}
                      />
                      <span className="slider round"></span>
                    </label>
                  </div>

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
            <button className="clear-history-btn" onClick={clearChat} title="清除目前對話紀錄">
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
                      {SAMPLE_QUESTIONS.map((question) => (
                        <li key={question}>
                          <button
                            type="button"
                            className="sample-question-btn"
                            onClick={() => handleSampleQuestion(question)}
                          >
                            {question}
                          </button>
                        </li>
                      ))}
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
                      onClick={handleMessageContentClick}
                    />
                    
                    {/* 來源卡片 */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="sources-section">
                        <div className="sources-title">📌 系統檢索來源：</div>
                        <div className="sources-list">
                          {[...new Set(msg.sources)].map((src, sIdx) => (
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
            {inputHelpText && (
              <div className="input-help-text">{inputHelpText}</div>
            )}
            <div className="chat-input-row">
              <input
                ref={inputRef}
                type="text"
                placeholder={inputPlaceholder}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={isLoading || !canAskQuestion}
              />
              <button 
                type="submit" 
                disabled={!input.trim() || isLoading || !canAskQuestion}
                className="send-btn"
                title={canAskQuestion ? "送出問題" : "請先確認後端與知識庫狀態"}
                aria-label="送出問題"
              >
                <span>{isLoading ? "思考中" : "發送"}</span>
                <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                  <path fill="currentColor" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                </svg>
              </button>
            </div>
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
