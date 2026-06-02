import os
import json
import jieba
import subprocess
import urllib.request
import time
from typing import Optional

def ensure_ollama_running():
    """檢查本地 Ollama 服務是否啟動，若未啟動則嘗試在 macOS 上自動開啟它"""
    ollama_url = "http://localhost:11434"
    try:
        # 嘗試在 1 秒內檢測 Ollama 服務是否正常
        with urllib.request.urlopen(ollama_url, timeout=1.0) as response:
            if response.status == 200:
                return True
    except Exception:
        # 服務未啟動，嘗試啟動
        print("🤖 偵測到地端 Ollama 未啟動，嘗試自動開啟 Ollama 應用程式...")
        try:
            # 在 macOS 上使用 open -a 啟動應用程式
            subprocess.Popen(["open", "-a", "Ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # 輪詢等待，直到服務啟動（最多等待 15 秒）
            for i in range(15):
                time.sleep(1.0)
                try:
                    with urllib.request.urlopen(ollama_url, timeout=1.0) as response:
                        if response.status == 200:
                            print("🎉 Ollama 服務已成功啟動！")
                            return True
                except Exception:
                    continue
            print("⚠️ Ollama 啟動時間較長，請稍後確認是否已在背景載入。")
        except Exception as e:
            print(f"❌ 無法自動啟動 Ollama: {e}。請手動開啟 Ollama 應用程式。")
    return False

from rank_bm25 import BM25Okapi
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate

# 使用相對於本檔案的絕對路徑，以防在不同工作目錄下啟動服務時導致路徑偏差
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
CHROMA_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")

# 主題關鍵字 → 優先來源文件映射表（用於 RRF 後的主題感知重排序）
# 解決問題：BM25 對英文 PDF（如請假規則）無法匹配中文問句，卻因「辦理」等通用詞
# 將社團章程等無關文件引入最終 context，導致 LLM 作答错誤
_TOPIC_SOURCE_MAP = [
    ({"請假", "事假", "病假", "婚假", "喪假", "產假", "陪產假", "公假", "缺課", "假期", "假別"},
     "6800ade9ad279805632161.pdf"),   # 東吳大學學生請假規則
    ({"工讀", "時薪", "工讀金", "打工", "助學工讀"},
     "6261123f68ff3747511986.pdf"),   # 東吳大學學生工讀助學實施辦法
    ({"宿舍", "住宿", "校外宿舍", "舍監"},
     "6418115967cf9033858547.pdf"),   # 東吳大學校外學生宿舍輔導及管理辦法
    ({"清寒", "急難", "救助金", "貧困"},
     "57eecfa622cfb319332789.pdf"),   # 東吳大學學生清寒急難救助金實施辦法
    ({"社團", "社員", "幹部", "社長"},
     "6228687cc02e7827840235.pdf"),   # 東吳大學學生社團組織及活動辦法
    ({"優秀應屆畢業生", "應屆", "畢業生選拔", "畢業生獎勵", "優秀畢業生"},
     "622864552d50a726687045.pdf"),   # 東吳大學優秀應屆畢業生選拔及獎勵辦法
    ({"甄選委員會", "章程", "委員會組織"},
     "57eecfa6815c1014215900.pdf"),   # 東吳大學獎助學金暨優秀學生甄選委員會組織章程
    ({"研究生", "研究生獎助學金"},
     "62286375884a8258956750.pdf"),   # 東吳大學研究生獎助學金辦法
    ({"碩士班新生", "博士班新生", "優秀新生", "新生獎勵"},
     "57eecfa5a8501458168219.pdf"),   # 東吳大學碩、博士班優秀新生獎勵辦法
    ({"銷過", "改過", "銷過實施"},
     "6228681d46e33141989956.pdf"),   # 東吳大學學生銷過實施辦法
    ({"會費", "學生會費", "代收會費"},
     "5b026ccaedc98902818150.pdf"),   # 東吳大學學生會會費代收辦法
    ({"端木愷", "端木愷獎學金"},
     "6926c31472b20396768425.pdf"),   # 東吳大學端木愷校長獎學金實施要點
    ({"獎懲委員會", "記過", "申訴", "懲處"},
     "57eecfa73a072014328000.pdf"),   # 東吳大學學生獎懲委員會組織章程
    ({"獎助學金申請", "審核辦法"},
     "57eecfa655a1a394937917.pdf"),   # 東吳大學獎助學金申請審核辦法
    ({"導師", "優良導師", "熱心導師", "績優導師"},
     "6228677210909078349219.pdf"),   # 東吳大學優良導師獎勵辦法
]

def _detect_priority_source(query: str) -> str:
    """根據問題關鍵字偵測應優先排序的主題文件（返回檔名，無匹配返回空字串）"""
    for keywords, source_file in _TOPIC_SOURCE_MAP:
        if any(kw in query for kw in keywords):
            return source_file
    return ""


# 確保 PDF 目錄存在
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

_embeddings = None
_llm = None
_db = None
_ollama_checked = False
_status_cache = None
_status_cache_at = 0.0
_STATUS_CACHE_TTL_SECONDS = 5.0
_bm25_cache = {
    "db_id": None,
    "pdf_texts": [],
    "pdf_metadatas": [],
    "bm25_pdf": None,
}
_title_mapping_cache = {
    "mtime_ns": None,
    "mapping": {},
}
_faq_count_cache = {
    "signature": None,
    "count": 0,
}
_filter_support_cache = {}

def _get_pdf_files() -> list:
    return sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".pdf")]) if os.path.exists(DATA_DIR) else []

def _get_faq_signature() -> Optional[dict]:
    faq_cache_path = os.path.join(DATA_DIR, "faq_cache.json")
    if not os.path.exists(faq_cache_path):
        return None
    stat = os.stat(faq_cache_path)
    return {
        "file": "faq_cache.json",
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }

def _build_db_meta(pdf_files: list) -> dict:
    return {
        "files": pdf_files,
        "faq_signature": _get_faq_signature(),
    }

def _is_db_meta_current(db_meta: dict, pdf_files: list) -> bool:
    return db_meta.get("files", []) == pdf_files and db_meta.get("faq_signature") == _get_faq_signature()

def _clear_runtime_caches(clear_db: bool = False):
    global _db, _status_cache, _status_cache_at, _bm25_cache, _filter_support_cache
    if clear_db:
        _db = None
    _status_cache = None
    _status_cache_at = 0.0
    _bm25_cache = {
        "db_id": None,
        "pdf_texts": [],
        "pdf_metadatas": [],
        "bm25_pdf": None,
    }
    _filter_support_cache = {}

def _clean_pdf_text(text: str) -> str:
    """修正常見 PDF ligature/編碼破碎字元。"""
    if not text:
        return text
    replacements = {
        '\u014c': 'ft',  # Ō -> ft (after)
        '\u019f': 'ti',  # Ɵ -> ti (national)
        '\u01a9': 'tt',  # Ʃ -> tt (attend)
        '\ufb00': 'ff',
        '\ufb01': 'fi',
        '\ufb02': 'fl',
        '\ufb03': 'ffi',
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text

def _get_title_mapping() -> dict:
    """讀取並快取檔名到法規標題的對照表。"""
    global _title_mapping_cache
    mapping_path = os.path.join(os.path.dirname(__file__), 'title_mapping.json')
    if not os.path.exists(mapping_path):
        _title_mapping_cache = {"mtime_ns": None, "mapping": {}}
        return {}

    mtime_ns = os.stat(mapping_path).st_mtime_ns
    if _title_mapping_cache["mtime_ns"] == mtime_ns:
        return _title_mapping_cache["mapping"]

    try:
        with open(mapping_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
    except Exception:
        mapping = {}

    _title_mapping_cache = {
        "mtime_ns": mtime_ns,
        "mapping": mapping,
    }
    return mapping

def _get_faq_count() -> int:
    """統計 FAQ 題數，並依 faq_cache.json 簽章快取結果。"""
    global _faq_count_cache
    signature = _get_faq_signature()
    if _faq_count_cache["signature"] == signature:
        return _faq_count_cache["count"]

    faq_count = 0
    faq_cache_path = os.path.join(DATA_DIR, "faq_cache.json")
    if signature is not None:
        try:
            with open(faq_cache_path, 'r', encoding='utf-8') as f:
                faq_cache = json.load(f)
            for entry in faq_cache.values():
                faq_count += len([q for q in entry.get("faqs", []) if q.strip()])
        except Exception:
            faq_count = 0

    _faq_count_cache = {
        "signature": signature,
        "count": faq_count,
    }
    return faq_count

def get_embeddings():
    """延遲載入並取得地端嵌入模型，只在需要時檢查 Ollama"""
    global _embeddings, _ollama_checked
    if _embeddings is None:
        if not _ollama_checked:
            ensure_ollama_running()
            _ollama_checked = True
        # 初始化地端嵌入模型
        # 使用 Ollama 的 nomic-embed-text，此模型專為文本嵌入設計，適合地端高效執行。
        _embeddings = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url="http://localhost:11434"
        )
    return _embeddings

def get_llm():
    """延遲載入並取得地端 LLM，只在需要時檢查 Ollama"""
    global _llm, _ollama_checked
    if _llm is None:
        if not _ollama_checked:
            ensure_ollama_running()
            _ollama_checked = True
        # 初始化地端 LLM 引擎 (使用 gemma3)
        _llm = ChatOllama(
            model="gemma3",
            base_url="http://localhost:11434",
            temperature=0.0  # 設為 0 以獲得最穩定、不隨機且不產生幻覺的回答
        )
    return _llm

def init_vector_db(force_rebuild: bool = False):
    """初始化並建立向量資料庫，並在 PDF 檔案有變動時自動重建"""
    global _db

    # 檢查是否有 PDF 檔案
    pdf_files = _get_pdf_files()
    
    # 記錄已加載的 PDF 列表的 meta 檔路徑
    meta_path = os.path.join(CHROMA_DIR, "db_meta.json")
    
    need_rebuild = force_rebuild
    
    # 檢查資料庫是否存在
    if not need_rebuild:
        if not os.path.exists(CHROMA_DIR) or len(os.listdir(CHROMA_DIR)) == 0:
            need_rebuild = True
        else:
            # 檢查 meta 檔
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        db_meta = json.load(f)
                    # 如果 PDF 或 FAQ 快取簽章不一致，需要重建
                    if not _is_db_meta_current(db_meta, pdf_files):
                        need_rebuild = True
                except Exception:
                    need_rebuild = True
            else:
                need_rebuild = True

    if _db is not None and not need_rebuild:
        return _db
                
    # 如果需要重建且有 PDF 檔案，先刪除舊庫並重建
    if need_rebuild and pdf_files:
        print("🔄 偵測到 PDF 或 FAQ 檔案變動，正在重建向量資料庫...")
        import shutil
        _clear_runtime_caches(clear_db=True)
        if os.path.exists(CHROMA_DIR):
            try:
                shutil.rmtree(CHROMA_DIR)
            except Exception as e:
                print(f"⚠️ 刪除舊向量庫失敗: {e}，將嘗試直接覆蓋。")
            
        from langchain_community.document_loaders import PyPDFDirectoryLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        
        loader = PyPDFDirectoryLoader(DATA_DIR)
        documents = loader.load()
        
        # 終極 PDF 編碼與 Ligature 合字清洗器，還原被破壞的英文單字，使地端 LLM 能正確閱讀理解
        for doc in documents:
            if doc.page_content:
                doc.page_content = _clean_pdf_text(doc.page_content)
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        chunks = text_splitter.split_documents(documents)
        
        # 【FAQ 口語問題整合】讀取 faq_cache.json，將每個口語問題作為獨立 Document 嵌入
        # 這讓使用者用口語提問時能命中正確的法規 chunk，實現「雙路向量檢索」
        faq_cache_path = os.path.join(DATA_DIR, "faq_cache.json")
        faq_docs = []
        if os.path.exists(faq_cache_path):
            try:
                with open(faq_cache_path, 'r', encoding='utf-8') as f:
                    faq_cache = json.load(f)
                for entry in faq_cache.values():
                    source_name = entry.get("source", "未知來源")
                    page = entry.get("page", 1)
                    original_content = entry.get("content", "")
                    
                    # 對既有快取中的原文做終極防禦性 Ligature 清洗，還原破碎英文
                    original_content = _clean_pdf_text(original_content)
                        
                    for faq_q in entry.get("faqs", []):
                        if faq_q.strip():
                            faq_docs.append(Document(
                                page_content=faq_q.strip(),
                                metadata={
                                    "source": os.path.join(DATA_DIR, source_name),
                                    "page": page - 1,  # LangChain page 索引從 0 開始
                                    "faq_question": faq_q.strip(),
                                    "original_content": original_content,
                                    "is_faq": True  # 顯式標記，用於 Python 層過濾
                                }
                            ))
                print(f"✅ 已整合 {len(faq_docs)} 個口語 FAQ 問題到向量資料庫。")
            except Exception as e:
                print(f"⚠️ 讀取 FAQ 快取失敗，跳過 FAQ 整合: {e}")
        
        all_docs = chunks + faq_docs
        db = Chroma.from_documents(
            documents=all_docs,
            embedding=get_embeddings(),
            persist_directory=CHROMA_DIR
        )
        
        # 建立 meta 檔以記錄載入的檔案
        os.makedirs(CHROMA_DIR, exist_ok=True)
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(_build_db_meta(pdf_files), f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"⚠️ 寫入 db_meta.json 失敗: {e}")
            
        _db = db
        return db
    
    # 如果不需要重建且資料庫存在，直接載入
    if os.path.exists(CHROMA_DIR) and len(os.listdir(CHROMA_DIR)) > 0:
        _db = Chroma(persist_directory=CHROMA_DIR, embedding_function=get_embeddings())
        return _db
    
    return None

def check_vector_db_status() -> dict:
    """檢查向量資料庫的狀態與 PDF 文件是否一致"""
    pdf_files = _get_pdf_files()
    
    if not pdf_files:
        return {"status": "empty", "files": []}
        
    meta_path = os.path.join(CHROMA_DIR, "db_meta.json")
    
    # 檢查資料庫目錄是否存在且有內容
    if not os.path.exists(CHROMA_DIR) or len(os.listdir(CHROMA_DIR)) == 0:
        return {"status": "outdated", "files": pdf_files}
        
    # 檢查 meta 檔
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                db_meta = json.load(f)
            if _is_db_meta_current(db_meta, pdf_files):
                return {"status": "ready", "files": pdf_files}
            else:
                return {"status": "outdated", "files": pdf_files}
        except Exception:
            return {"status": "outdated", "files": pdf_files}
    else:
        return {"status": "outdated", "files": pdf_files}

def generate_expanded_queries(user_query: str, api_key: str = None) -> list:
    """利用 LLM 將使用者查詢擴展為多個檢索句"""
    queries = [user_query]
    
    # 判斷是否為請假/缺席相關的問題，若是才啟用中英雙語擴展
    is_leave_query = any(k in user_query.lower() for k in ["假", "leave", "absent", "vacation", "sick"])
    
    # 為了節省算力與時間，非請假問題若長度大於 30 字，則直接返回不進行擴展
    if not is_leave_query and len(user_query.strip()) > 30:
        return queries
    
    # 【地端零延遲雙語擴展優化】
    # 若為純地端模式且沒有 API 金鑰，呼叫本地 LLM 做擴展會耗費 3~5 秒。
    # 這裡採用旁路機制：非請假問題不需英文，直接跳過擴充；請假問題使用靜態規則詞庫擴充，耗時 0 毫秒！
    if not api_key:
        if is_leave_query:
            # 針對請假規則，進行靜態跨語言檢索詞補強，區分一般請假與考試請假
            is_exam_query = any(k in user_query for k in ["考", "exam", "test", "midterm", "final"])
            if is_exam_query:
                queries.extend(["examination leave regulations", "final exam leave of absence", "makeup exam request"])
            else:
                queries.extend(["student leave regulations", "leave of absence", "absent from class"])
            return queries[:4]
        else:
            return queries
            
    if is_leave_query:
        prompt = (
            f"請將使用者的搜尋詞「{user_query}」進行擴展，生成 3 個適合法規與文件檢索的搜尋句。\n"
            "【要求】：\n"
            "1. 必須與原問句高度相關。\n"
            "2. 其中 1 個必須為純中文搜尋句或關鍵字組合，另外 2 個必須為純英文搜尋句或關鍵字組合（例如將問題中的核心名詞與語意精準翻譯成英文）。\n"
            "3. 僅輸出這 3 個擴展後的搜尋句（1個中文，2個英文），每行一個，前面不要加上序號、引號或任何多餘的解釋文字。\n"
        )
    else:
        prompt = (
            f"請將使用者的搜尋詞「{user_query}」進行擴展，生成 3 個適合法規與文件檢索的中文搜尋句。\n"
            "【要求】：\n"
            "1. 必須與原問句高度相關。\n"
            "2. 僅輸出這 3 個擴展後的中文搜尋句，每行一個，前面不要加上序號、引號或任何多餘的解釋文字。\n"
        )
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        response = model.generate_content(prompt, generation_config={"temperature": 0.2})
        text = response.text
            
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            cleaned = line
            if cleaned.startswith(("1.", "2.", "3.", "4.", "5.", "-", "*")):
                cleaned = cleaned.split(".", 1)[-1].split("*", 1)[-1].split("-", 1)[-1].strip()
            if cleaned and cleaned != user_query:
                queries.append(cleaned)
    except Exception as e:
        print(f"⚠️ 查詢擴展失敗，將僅使用原問句進行檢索: {e}")
        
    return queries[:4]

def rrf_fusion(dense_results_list: list, sparse_results_list: list, k: int = 60) -> list:
    """倒數排序融合 (RRF) 演算法"""
    rrf_scores = {}
    doc_map = {}
    
    def add_ranks(results_list):
        for results in results_list:
            for rank, doc in enumerate(results):
                doc_id = doc.page_content
                doc_map[doc_id] = doc
                if doc_id not in rrf_scores:
                    rrf_scores[doc_id] = 0.0
                rrf_scores[doc_id] += 1.0 / (k + rank + 1)
                
    add_ranks(dense_results_list)
    add_ranks(sparse_results_list)
    
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[doc_id] for doc_id, score in sorted_docs]

def _get_pdf_bm25_index(db) -> dict:
    """取得 PDF chunk 的 BM25 索引；同一個 Chroma 實例只建立一次。"""
    global _bm25_cache
    if _bm25_cache["db_id"] == id(db):
        return _bm25_cache

    all_data = db.get()
    all_texts = all_data.get("documents", [])
    all_metadatas = all_data.get("metadatas", [])

    pdf_texts = []
    pdf_metadatas = []
    for txt, meta in zip(all_texts, all_metadatas):
        if not meta.get("faq_question"):
            pdf_texts.append(txt)
            pdf_metadatas.append(meta)

    bm25_pdf = None
    if pdf_texts:
        tokenized_pdf_corpus = [list(jieba.cut(doc)) for doc in pdf_texts]
        bm25_pdf = BM25Okapi(tokenized_pdf_corpus)

    _bm25_cache = {
        "db_id": id(db),
        "pdf_texts": pdf_texts,
        "pdf_metadatas": pdf_metadatas,
        "bm25_pdf": bm25_pdf,
    }
    return _bm25_cache

def _filter_cache_key(filter_metadata: dict) -> str:
    return json.dumps(filter_metadata, sort_keys=True, ensure_ascii=False)

def _split_dense_docs_by_type(docs: list) -> tuple:
    docs_faq = [d for d in docs if d.metadata.get("is_faq") is True]
    docs_pdf = [d for d in docs if d.metadata.get("is_faq") is not True]
    return docs_faq, docs_pdf

def _similarity_search_with_optional_filter(db, query: str, k: int, filter_metadata: dict, fallback_on_empty: bool = True) -> tuple:
    """嘗試使用 Chroma metadata filter；不可用時回傳 ([], False) 讓上層走安全 fallback。"""
    global _filter_support_cache
    cache_key = _filter_cache_key(filter_metadata)
    if _filter_support_cache.get(cache_key) is False:
        return [], False

    try:
        docs = db.similarity_search(query, k=k, filter=filter_metadata)
        if fallback_on_empty and not docs:
            _filter_support_cache[cache_key] = False
            return [], False
        _filter_support_cache[cache_key] = True
        return docs, True
    except Exception as e:
        print(f"⚠️ Chroma metadata filter 不可用，改用 Python 層分類 fallback: {e}")
        _filter_support_cache[cache_key] = False
        return [], False

def _retrieve_dense_candidates(db, query: str) -> tuple:
    """雙路 dense 檢索：優先 metadata filter，失敗時退回 k=30 全量候選分類。"""
    faq_docs, faq_filter_ok = _similarity_search_with_optional_filter(
        db,
        query,
        k=4,
        filter_metadata={"is_faq": True},
    )
    pdf_docs, pdf_filter_ok = _similarity_search_with_optional_filter(
        db,
        query,
        k=8,
        filter_metadata={"is_faq": {"$ne": True}},
    )

    if faq_filter_ok and pdf_filter_ok:
        return faq_docs[:4], pdf_docs[:8]

    fallback_docs = db.similarity_search(query, k=30)
    fallback_faq_docs, fallback_pdf_docs = _split_dense_docs_by_type(fallback_docs)

    if not faq_filter_ok:
        faq_docs = fallback_faq_docs[:4]
    if not pdf_filter_ok:
        pdf_docs = fallback_pdf_docs[:8]

    return faq_docs[:4], pdf_docs[:8]

def query_rag_stream(user_query: str, api_key: str = None, db = None, disable_expansion: bool = False):
    """查詢 RAG 系統並以生成器方式返回 metadata 與答案字元流 (支援 RRF 融合排序、查詢擴展與 Gemini API 備援)"""
    # 1. 檢索本地向量資料庫（PDF 知識庫）
    if db is None:
        db = init_vector_db()
        
    if db is None:
        yield {
            "type": "error",
            "content": "抱歉，目前系統知識庫為空。請先在 `data/` 資料夾下放入 PDF 檔案以建立知識庫。"
        }
        return
        
    # 2. 進行查詢擴展
    if disable_expansion:
        # 【加速模式特例優化】即使開啟了加速模式，如果是需要跨語檢索的請假問題，也必須進行基本雙語擴展，否則無法檢索英文 PDF。
        # 由於地端擴充已採用零延遲旁路詞庫，此處強制保留請假問題的擴展。
        is_leave_query = any(k in user_query.lower() for k in ["假", "leave", "absent", "vacation", "sick"])
        if is_leave_query:
            queries = generate_expanded_queries(user_query, api_key)
        else:
            queries = [user_query]
    else:
        queries = generate_expanded_queries(user_query, api_key)
    
    # 3. 取得快取過的 PDF BM25 索引（避免每題都重建稀疏檢索語料庫）
    bm25_index = _get_pdf_bm25_index(db)
    pdf_texts = bm25_index["pdf_texts"]
    pdf_metadatas = bm25_index["pdf_metadatas"]
    bm25_pdf = bm25_index["bm25_pdf"]

    # 4. 多重查詢檢索（雙庫分離策略：FAQ 語意命中 + PDF 法規原文）
    # 使用 Python 層手動過濾，一次取 k=20 結果後分類
    faq_dense_lists = []    # FAQ 口語問題命中結果
    pdf_dense_lists = []    # PDF 法規原文命中結果
    pdf_sparse_lists = []   # PDF BM25 關鍵字命中結果
    
    for q in queries:
        docs_faq_q, docs_pdf_q = _retrieve_dense_candidates(db, q)
        
        if docs_faq_q:
            faq_dense_lists.append(docs_faq_q)
        if docs_pdf_q:
            pdf_dense_lists.append(docs_pdf_q)
        
        # PDF BM25 關鍵字搜尋（只在 PDF chunk 語料庫中搜尋）
        if bm25_pdf and pdf_texts:
            tokenized_q = list(jieba.cut(q))
            scores = bm25_pdf.get_scores(tokenized_q)
            top_n_idx = bm25_pdf.get_top_n(tokenized_q, range(len(pdf_texts)), n=4)
            docs_sparse = []
            for idx in top_n_idx:
                if scores[idx] > 0:
                    docs_sparse.append(Document(page_content=pdf_texts[idx], metadata=pdf_metadatas[idx]))
            pdf_sparse_lists.append(docs_sparse)

            
    # 5. RRF 倒數排序融合與去重
    # 先對 PDF chunks 進行 RRF 融合
    merged_pdf_docs = rrf_fusion(pdf_dense_lists, pdf_sparse_lists, k=60)
    
    # 主題感知重排序：偵測到特定主題關鍵字時，將對應文件的 chunks 置頂
    # 原理：Dense 搜尋語義跨語言正確，但 BM25 因通用詞（如「辦理」）命中無關中文文件（如社團章程），
    # RRF 融合後可能將錯誤文件置於最終 context。此步驟在 RRF 後修正排序，確保主題對應文件優先。
    _priority_src = _detect_priority_source(user_query)
    if _priority_src:
        _prio_docs = [d for d in merged_pdf_docs if _priority_src in d.metadata.get("source", "")]
        _other_docs = [d for d in merged_pdf_docs if _priority_src not in d.metadata.get("source", "")]
        merged_pdf_docs = _prio_docs + _other_docs
    
    pdf_docs = merged_pdf_docs[:4]  # 取前 4 個最相關法規 chunk
    
    # 取最相關的 FAQ 命中（最多 3 個，避免單一 query 的第一名被其他法規 FAQ 競爭排擠）
    faq_docs_result = []
    if faq_dense_lists:
        seen = set()
        for faq_list in faq_dense_lists:
            for d in faq_list[:3]:  # 擴大至前 3 名 FAQ 候選
                if d.page_content not in seen:
                    seen.add(d.page_content)
                    faq_docs_result.append(d)
        faq_docs_result = faq_docs_result[:3]  # 最多保留 3 個 FAQ 命中，提高容錯率
    
    # 合併：FAQ 命中放前面（若有命中），再加 PDF chunks
    docs = faq_docs_result + pdf_docs
    
    # 主題感知淨化過濾器：若偵測到特定主題文件，且檢索結果中包含此文件，則精準排除無關文件，避免地端模型混淆
    if _priority_src:
        purified_docs = [d for d in docs if _priority_src in d.metadata.get("source", "")]
        if purified_docs:
            docs = purified_docs
            print(f"🎯 觸發主題感知淨化過濾器，僅保留與主題 {_priority_src} 相關的 {len(docs)} 個 chunks，排除其他無關法規。")
            
    docs = docs[:7]  # 最多 7 個 context chunks（3 FAQ + 4 PDF）

    
    if not docs:
        yield {
            "type": "error",
            "content": "抱歉，從現有法規中找不到與您問題相關的解答。"
        }
        return
        
    # 載入檔名與真實標題的映射
    title_mapping = _get_title_mapping()
            
    # 合併檢索到的 context 文字與資訊來源
    context_parts = []
    sources = []
    detailed_sources = []
    
    for doc in docs:
        src = doc.metadata.get("source", "未知來源")
        source_name = os.path.basename(src)
        page = doc.metadata.get("page", 0) + 1  # LangChain page 索引從 0 開始
        
        friendly_title = title_mapping.get(source_name, source_name)
        
        # 判斷此 chunk 是否為 FAQ 口語問題（有 faq_question metadata）
        faq_question = doc.metadata.get("faq_question", None)
        # 若為 FAQ doc，使用儲存的法規原文作為 context；否則直接使用 chunk 本身
        original_content = doc.metadata.get("original_content", None)
        display_content = original_content if (faq_question and original_content) else doc.page_content
        
        # 偵測內容語言：若英文字母比例超過 70%，加上跨語言提示標注，幫助 LLM 正確理解
        english_alpha = sum(1 for c in display_content if c.isascii() and c.isalpha())
        total_alpha = sum(1 for c in display_content if c.isalpha())
        is_english = total_alpha > 0 and (english_alpha / total_alpha) > 0.7
        lang_note = " [⚠️ 英文原文：請閱讀理解語意後以中文回答，不可因語言不同說找不到]" if is_english else ""
            
        context_parts.append(f"[來源檔案: {friendly_title} (第 {page} 頁){lang_note}]\n{display_content}")
        
        source_info = f"{friendly_title} (第 {page} 頁)"
        if source_info not in sources:
            sources.append(source_info)
        
        ds_entry = {
            "title": source_info,
            "content": display_content
        }
        if faq_question:
            ds_entry["hit_faq"] = faq_question
        detailed_sources.append(ds_entry)
            
    context_text = "\n\n".join(context_parts)
    
    # 先傳回檢索到的 metadata 供 UI 預先處理
    yield {
        "type": "metadata",
        "sources": sources,
        "detailed_sources": detailed_sources,
        "engine_type": "API 加速模式 ⚡" if api_key else "地端模式 🦉",
        "expanded_queries": queries
    }
    
    # 6. 設計地端 RAG Prompt
    system_prompt = (
        "你是一位嚴謹的東吳大學學生事務知識庫助手。請根據以下提供的 Context（法規或問答內容）精準回答使用者的問題。\n"
        "【嚴格要求】：\n"
        "1. **完全基於事實**：僅根據 Context 內有的內容回答。不可憑空想像、推論或加入外部知識。答案必須精準，不可過度推論。若 Context 中包含原則性規定（如「由委員會另訂之」、「以基本工資為原則」），請如實回答，不可回答找不到。\n"
        "2. **明確標註來源**：必須在回答中提及參考的資料來源（檔名與頁數，例如：學生請假規則第 3 頁）。\n"
        "3. **拒答處理**：若 Context 完全無關且找不到答案，請僅回答：「抱歉，在現有的企業知識庫中找不到與您問題相關的解答」，不准附帶其他多餘字句。\n"
        "4. **跨語言對照翻譯**：Context 若為英文，必須以中文作答。翻譯請使用台灣大專院校慣用語：\n"
        "   - Academic Affairs Office -> **教務處**\n"
        "   - Student Affairs Office -> **學務處**\n"
        "   - department chair -> **學系主任**\n"
        "   - semester examinations -> **學期考試（期末考）**\n"
        "   - temporary exams or midterms -> **臨時考試或期中考**\n"
        "5. **嚴防期限與核定單位混淆**：不同假別（如「一般請假」與「學期考試請假」）的期限與核准單位分屬不同條文，**絕對不可混用**。請根據使用者所問的具體假別，找到該假別專屬的條文與期限進行回答：\n"
        "   - **一般請假（如事假、病假、生理假等）**：最遲應於缺課次日起**一週內**完成辦理。\n"
        "   - **學期考試（期末考）請假**：必須在考試結束後**五個工作日內**提出申請，由學系主任簽註意見並送**教務處**核定。\n"
        "6. **排版格式**：請務必使用 Markdown 格式回答。\n"
        "   - 對於回答中的**關鍵人名、日期、期限、分數、金額、假別、審核與核准單位**，必須使用雙星號（例如：**五個工作日**、**80分(含)以上**、**新臺幣3萬元**、**教務處**）進行粗體標注，以便系統進行螢光標記。\n"
        "   - 適當使用條列式與分段，使答案清晰易讀。\n\n"
        "Context:\n"
        "{context}"
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}")
    ])
    
    # 7. 呼叫 LLM 進行生成（包含 Gemini API 與地端 Ollama 備援降級邏輯）
    use_gemini = False
    has_yielded_content = False
    
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system_prompt.replace("{context}", context_text)
            )
            response = model.generate_content(
                user_query,
                generation_config={"temperature": 0.0},
                safety_settings=safety_settings,
                stream=True
            )
            for chunk in response:
                # 某些情況下取得 chunk.text 會因被阻擋或出錯而拋出異常，用 try-except 保護
                try:
                    text_content = chunk.text
                except Exception:
                    text_content = ""
                
                if text_content:
                    has_yielded_content = True
                    yield {
                        "type": "content",
                        "content": text_content
                    }
            use_gemini = True
        except Exception as e:
            print(f"⚠️ Gemini API 串流失敗: {e}")
            if not has_yielded_content:
                # 一個字都還沒輸出，代表是初始連線問題或 API 金鑰失效，此時可以安全降級地端
                print("🔄 偵測到一開始就出錯，自動降級至地端 Ollama 模式。")
                yield {
                    "type": "metadata",
                    "sources": sources,
                    "detailed_sources": detailed_sources,
                    "engine_type": "地端模式 🦉 (API 降級)"
                }
            else:
                # 已經輸出過內容，說明是中途斷掉或安全過濾，禁止再降級，避免拼接打架
                print("⚠️ 已經輸出過內容，為避免答案拼接打架，中止並直接收尾。")
                use_gemini = True  # 標記為 True 阻擋後面進入地端 block
                yield {
                    "type": "content",
                    "content": "\n\n*(⚠️ 回答因 API 額度限額、網路中斷或安全機制篩選而未完整生成)*"
                }
            
    if not use_gemini:
        # 呼叫地端 Ollama 串流
        formatted_prompt = prompt.invoke({"context": context_text, "input": user_query})
        for chunk in get_llm().stream(formatted_prompt):
            if chunk.content:
                yield {
                    "type": "content",
                    "content": chunk.content
                }

def query_rag(user_query: str, api_key: str = None, db = None, disable_expansion: bool = False) -> dict:
    """查詢 RAG 系統並返回答案與來源 (支援 RRF 融合排序、查詢擴展與 Gemini API 備援)"""
    generator = query_rag_stream(user_query, api_key=api_key, db=db, disable_expansion=disable_expansion)
    
    answer_parts = []
    sources = []
    detailed_sources = []
    engine_type = "地端模式 🦉"
    expanded_queries = []
    
    for item in generator:
        if item["type"] == "metadata":
            sources = item.get("sources", [])
            detailed_sources = item.get("detailed_sources", [])
            engine_type = item.get("engine_type", "地端模式 🦉")
            expanded_queries = item.get("expanded_queries", [])
        elif item["type"] == "content":
            answer_parts.append(item["content"])
        elif item["type"] == "error":
            return {
                "answer": item["content"],
                "sources": [],
                "detailed_sources": [],
                "engine_type": "未啟動",
                "expanded_queries": []
            }
            
    return {
        "answer": "".join(answer_parts),
        "sources": sources,
        "detailed_sources": detailed_sources,
        "engine_type": engine_type,
        "expanded_queries": expanded_queries
    }

def get_full_system_status() -> dict:
    """彙整並回傳系統完整狀態，包括向量庫健康度、載入法規名稱、FAQ 數量與 Ollama 狀態"""
    global _status_cache, _status_cache_at

    now = time.time()
    if _status_cache is not None and now - _status_cache_at < _STATUS_CACHE_TTL_SECONDS:
        return dict(_status_cache)

    # 1. 取得向量庫狀態與原始 PDF 列表
    db_status_info = check_vector_db_status()
    db_status = db_status_info.get("status", "empty")
    raw_files = db_status_info.get("files", [])
    
    # 2. 載入標題對照表並轉換檔名
    title_mapping = _get_title_mapping()
            
    loaded_files = [title_mapping.get(f, f) for f in raw_files]
    
    # 3. 統計 FAQ 數量
    faq_count = _get_faq_count()
            
    # 4. 偵測 Ollama 在線狀態 (不嘗試自動開啟，僅快速探測)
    ollama_status = "offline"
    try:
        with urllib.request.urlopen("http://localhost:11434", timeout=0.5) as response:
            if response.status == 200:
                ollama_status = "online"
    except Exception:
        pass
        
    status = {
        "db_status": db_status,
        "pdf_count": len(raw_files),
        "faq_count": faq_count,
        "ollama_status": ollama_status,
        "loaded_files": loaded_files
    }
    _status_cache = dict(status)
    _status_cache_at = now
    return status
