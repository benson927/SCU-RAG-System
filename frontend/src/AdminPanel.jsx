import { useCallback, useEffect, useState } from "react";
import "./AdminPanel.css";

const TOKEN_KEY = "scuAdminToken";

const formatDate = (value) => {
  if (!value) return "未設定";
  return new Intl.DateTimeFormat("zh-TW", {
    dateStyle: "medium",
    timeStyle: value.includes?.("T") ? "short" : undefined,
  }).format(new Date(value));
};

const formatBytes = (value) => {
  if (!Number.isFinite(value)) return "-";
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

function AdminPanel({ apiBaseUrl, onClose }) {
  const [token, setToken] = useState(sessionStorage.getItem(TOKEN_KEY) || "");
  const [password, setPassword] = useState("");
  const [documents, setDocuments] = useState([]);
  const [latestJob, setLatestJob] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [newDocument, setNewDocument] = useState({
    title: "",
    version_number: "",
    effective_date: "",
    file: null,
  });
  const [versionDrafts, setVersionDrafts] = useState({});

  const apiRequest = useCallback(async (path, options = {}) => {
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers });
    if (response.status === 401) {
      sessionStorage.removeItem(TOKEN_KEY);
      setToken("");
      throw new Error("管理者登入已失效，請重新登入。");
    }
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = await response.json();
        message = data.detail || message;
      } catch {
        // Keep the HTTP fallback.
      }
      throw new Error(message);
    }
    if (response.status === 204) return null;
    return response.json();
  }, [apiBaseUrl, token]);

  const loadDocuments = useCallback(async (silent = false) => {
    if (!token) return;
    if (!silent) setLoading(true);
    try {
      const data = await apiRequest("/api/admin/documents");
      setDocuments(data.documents || []);
      setLatestJob(data.latest_index_job || null);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [apiRequest, token]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void loadDocuments();
    }, 0);
    return () => window.clearTimeout(initialLoad);
  }, [loadDocuments]);

  useEffect(() => {
    if (!token || !latestJob || !["pending", "running"].includes(latestJob.status)) return undefined;
    const interval = window.setInterval(() => {
      void loadDocuments(true);
    }, 2000);
    return () => window.clearInterval(interval);
  }, [latestJob, loadDocuments, token]);

  const login = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "登入失敗");
      sessionStorage.setItem(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setPassword("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
    setDocuments([]);
    setLatestJob(null);
  };

  const buildFormData = (values, includeTitle = false) => {
    const form = new FormData();
    if (includeTitle) form.append("title", values.title);
    form.append("version_number", values.version_number);
    if (values.effective_date) form.append("effective_date", values.effective_date);
    form.append("file", values.file);
    return form;
  };

  const uploadDocument = async (event) => {
    event.preventDefault();
    if (!newDocument.file) return;
    setLoading(true);
    setError("");
    try {
      await apiRequest("/api/admin/documents", {
        method: "POST",
        body: buildFormData(newDocument, true),
      });
      setNewDocument({ title: "", version_number: "", effective_date: "", file: null });
      event.currentTarget.reset();
      setNotice("文件草稿已上傳，確認內容後即可發布。");
      await loadDocuments(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const uploadVersion = async (event, documentId) => {
    event.preventDefault();
    const draft = versionDrafts[documentId];
    if (!draft?.file) return;
    setLoading(true);
    setError("");
    try {
      await apiRequest(`/api/admin/documents/${documentId}/versions`, {
        method: "POST",
        body: buildFormData(draft),
      });
      setVersionDrafts((current) => ({ ...current, [documentId]: {} }));
      event.currentTarget.reset();
      setNotice("新版草稿已上傳。");
      await loadDocuments(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const runVersionAction = async (version, action) => {
    const labels = {
      publish: "發布這個版本",
      rollback: "回滾至這個版本",
      archive: "停用目前版本",
      delete: "永久刪除此草稿",
    };
    if (!window.confirm(`確定要${labels[action]}嗎？`)) return;
    setLoading(true);
    setError("");
    try {
      await apiRequest(`/api/admin/versions/${version.id}${action === "delete" ? "" : `/${action}`}`, {
        method: action === "delete" ? "DELETE" : "POST",
      });
      setNotice(action === "delete" ? "草稿已刪除。" : "操作已完成，索引工作正在背景執行。");
      await loadDocuments(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const retryIndexJob = async () => {
    if (!latestJob || latestJob.status !== "failed") return;
    setLoading(true);
    setError("");
    try {
      await apiRequest(`/api/admin/index-jobs/${latestJob.id}/retry`, { method: "POST" });
      setNotice("索引工作已重新排程。");
      await loadDocuments(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="admin-shell">
        <div className="admin-topbar">
          <div>
            <span className="admin-kicker">DOCUMENT CONTROL</span>
            <h2>法規文件管理後台</h2>
          </div>
          <button type="button" className="admin-secondary-btn" onClick={onClose}>返回問答</button>
        </div>
        <form className="admin-login-card" onSubmit={login}>
          <h3>管理者登入</h3>
          <p>管理密碼由後端環境變數 <code>ADMIN_PASSWORD</code> 設定。</p>
          <label>
            管理密碼
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && <div className="admin-alert error">{error}</div>}
          <button type="submit" className="admin-primary-btn" disabled={loading}>
            {loading ? "驗證中..." : "登入後台"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <div className="admin-topbar">
        <div>
          <span className="admin-kicker">DOCUMENT CONTROL</span>
          <h2>法規文件管理後台</h2>
          <p>PostgreSQL 管理版本，PDF 存放於 S3 相容物件儲存。</p>
        </div>
        <div className="admin-toolbar">
          <button type="button" className="admin-secondary-btn" onClick={() => loadDocuments()} disabled={loading}>重新整理</button>
          <button type="button" className="admin-secondary-btn" onClick={logout}>登出</button>
          <button type="button" className="admin-primary-btn" onClick={onClose}>返回問答</button>
        </div>
      </div>

      {error && <div className="admin-alert error">{error}</div>}
      {notice && <div className="admin-alert success">{notice}</div>}

      <details className="admin-guide" open>
        <summary>
          <span>
            <span className="admin-kicker">QUICK GUIDE</span>
            <strong>後台使用教學</strong>
          </span>
          <span className="guide-toggle">點擊收合</span>
        </summary>
        <div className="guide-steps">
          <div className="guide-step">
            <span className="guide-number">1</span>
            <div>
              <strong>新增文件</strong>
              <p>填寫標題、版本號與生效日期，選擇 PDF 後按「上傳草稿」。</p>
            </div>
          </div>
          <div className="guide-step">
            <span className="guide-number">2</span>
            <div>
              <strong>確認並發布</strong>
              <p>草稿尚未進入問答資料庫。確認無誤後，在版本右側按「發布」。</p>
            </div>
          </div>
          <div className="guide-step">
            <span className="guide-number">3</span>
            <div>
              <strong>等待索引完成</strong>
              <p>最新索引工作顯示 <code>succeeded</code> 後，新內容才可被 RAG 檢索。</p>
            </div>
          </div>
          <div className="guide-step">
            <span className="guide-number">4</span>
            <div>
              <strong>更新或復原</strong>
              <p>在原文件下方新增版本；可停用目前版本，或將 archived 舊版回滾。</p>
            </div>
          </div>
        </div>
        <div className="guide-notes">
          <span><b>draft</b> 草稿，可發布或刪除</span>
          <span><b>published</b> 目前生效且可被檢索</span>
          <span><b>archived</b> 歷史版本，可回滾</span>
        </div>
      </details>

      <section className="admin-status-grid">
        <div className="admin-stat-card">
          <span>文件數</span>
          <strong>{documents.length}</strong>
        </div>
        <div className="admin-stat-card">
          <span>已發布版本</span>
          <strong>{documents.reduce((count, document) => count + document.versions.filter((version) => version.status === "published").length, 0)}</strong>
        </div>
        <div className={`admin-stat-card job-${latestJob?.status || "none"}`}>
          <span>最新索引工作</span>
          <strong>{latestJob?.status || "尚無工作"}</strong>
          {latestJob?.error_message && <small>{latestJob.error_message}</small>}
          {latestJob?.status === "failed" && (
            <button type="button" className="admin-secondary-btn" onClick={retryIndexJob} disabled={loading}>
              重試索引
            </button>
          )}
        </div>
      </section>

      <section className="admin-card">
        <div className="admin-card-heading">
          <div>
            <span className="admin-kicker">NEW DOCUMENT</span>
            <h3>上傳新法規草稿</h3>
          </div>
          <p>上傳後不會立即進入 RAG，必須手動發布。</p>
        </div>
        <form className="admin-upload-form" onSubmit={uploadDocument}>
          <label>法規標題<input required value={newDocument.title} onChange={(event) => setNewDocument({ ...newDocument, title: event.target.value })} /></label>
          <label>版本號<input required placeholder="例如 2026.1" value={newDocument.version_number} onChange={(event) => setNewDocument({ ...newDocument, version_number: event.target.value })} /></label>
          <label>生效日期<input type="date" value={newDocument.effective_date} onChange={(event) => setNewDocument({ ...newDocument, effective_date: event.target.value })} /></label>
          <label className="admin-file-field">PDF 檔案<input required type="file" accept="application/pdf,.pdf" onChange={(event) => setNewDocument({ ...newDocument, file: event.target.files?.[0] || null })} /></label>
          <button type="submit" className="admin-primary-btn" disabled={loading || !newDocument.file}>上傳草稿</button>
        </form>
      </section>

      <section className="admin-document-list">
        {loading && documents.length === 0 && <div className="admin-empty">載入中...</div>}
        {!loading && documents.length === 0 && <div className="admin-empty">目前尚無文件，請先上傳第一份 PDF 草稿。</div>}
        {documents.map((document) => {
          const draft = versionDrafts[document.id] || {};
          return (
            <article className="admin-card document-card" key={document.id}>
              <div className="admin-card-heading">
                <div>
                  <span className="admin-kicker">LAW DOCUMENT</span>
                  <h3>{document.title}</h3>
                </div>
                <span className="version-count">{document.versions.length} 個版本</span>
              </div>

              <div className="version-timeline">
                {document.versions.map((version) => (
                  <div className={`version-row status-${version.status}`} key={version.id}>
                    <div className="version-dot" />
                    <div className="version-main">
                      <div className="version-title">
                        <strong>版本 {version.version_number}</strong>
                        <span className={`version-badge ${version.status}`}>{version.status}</span>
                      </div>
                      <div className="version-meta">
                        <span>{version.original_filename}</span>
                        <span>{formatBytes(version.size_bytes)}</span>
                        <span>生效：{formatDate(version.effective_date)}</span>
                        <span>建立：{formatDate(version.created_at)}</span>
                      </div>
                    </div>
                    <div className="version-actions">
                      {version.status === "draft" && (
                        <>
                          <button type="button" onClick={() => runVersionAction(version, "publish")}>發布</button>
                          <button type="button" className="danger" onClick={() => runVersionAction(version, "delete")}>刪除草稿</button>
                        </>
                      )}
                      {version.status === "published" && (
                        <button type="button" className="danger" onClick={() => runVersionAction(version, "archive")}>停用</button>
                      )}
                      {version.status === "archived" && (
                        <button type="button" onClick={() => runVersionAction(version, "rollback")}>回滾至此版</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <form className="admin-upload-form compact" onSubmit={(event) => uploadVersion(event, document.id)}>
                <label>新版號<input required value={draft.version_number || ""} onChange={(event) => setVersionDrafts((current) => ({ ...current, [document.id]: { ...draft, version_number: event.target.value } }))} /></label>
                <label>生效日期<input type="date" value={draft.effective_date || ""} onChange={(event) => setVersionDrafts((current) => ({ ...current, [document.id]: { ...draft, effective_date: event.target.value } }))} /></label>
                <label className="admin-file-field">新版 PDF<input required type="file" accept="application/pdf,.pdf" onChange={(event) => setVersionDrafts((current) => ({ ...current, [document.id]: { ...draft, file: event.target.files?.[0] || null } }))} /></label>
                <button type="submit" className="admin-secondary-btn" disabled={loading || !draft.file}>新增版本草稿</button>
              </form>
            </article>
          );
        })}
      </section>
    </div>
  );
}

export default AdminPanel;
