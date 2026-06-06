import os
import json
import jieba
import threading

from backend.config import get_settings

from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate
from backend.services.rag_models import ensure_ollama_running, get_embeddings, get_llm
from backend.services.rag_retrieval import (
    bm25_top_pdf_docs as _bm25_top_pdf_docs,
    dedupe_documents_by_identity as _dedupe_documents_by_identity,
    dedupe_queries as _dedupe_queries,
    doc_matches_source as _doc_matches_source,
    filter_cache_key as _filter_cache_key,
    get_pdf_bm25_index as _get_pdf_bm25_index,
    priority_source_pdf_docs as _priority_source_pdf_docs,
    reset_retrieval_caches,
    retrieve_dense_candidates as _retrieve_dense_candidates,
    rrf_fusion,
    similarity_search_with_optional_filter as _similarity_search_with_optional_filter,
    split_dense_docs_by_type as _split_dense_docs_by_type,
)
from backend.services.rag_repository import (
    CHROMA_DIR,
    DATA_DIR,
    MANAGED_DATA_DIR,
    MANAGED_MANIFEST_PATH,
    build_db_meta as _build_db_meta,
    clean_pdf_text as _clean_pdf_text,
    ensure_data_directory,
    get_faq_count as _get_faq_count,
    get_pdf_data_dir as _get_pdf_data_dir,
    get_pdf_files as _get_pdf_files,
    get_title_mapping as _get_title_mapping,
    is_db_meta_current as _is_db_meta_current,
    iter_active_faq_entries as _iter_active_faq_entries,
    load_managed_manifest as _load_managed_manifest,
    reset_repository_caches,
)
from backend.services.rag_status import (
    get_full_system_status as _get_full_system_status,
    reset_status_cache,
)

# 使用相對於本檔案的絕對路徑，以防在不同工作目錄下啟動服務時導致路徑偏差
_vector_db_lock = threading.RLock()

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

def _is_under_specified_query(query: str) -> bool:
    """判斷是否為過短或只像關鍵字的查詢，避免 RAG 對模糊詞硬生成答案。"""
    cleaned = query.strip()
    if not cleaned:
        return True

    question_markers = ("?", "？", "什麼", "如何", "怎麼", "幾", "多少", "是否", "可以", "能否", "期限", "標準", "條件", "辦法", "申請", "資格")
    if any(marker in cleaned for marker in question_markers):
        return False

    compact = "".join(cleaned.split())
    if len(compact) <= 4:
        return True

    tokens = [token for token in cleaned.replace("，", " ").replace(",", " ").split() if token]
    return len(tokens) == 1 and len(compact) <= 8

def _build_clarification_message(query: str) -> str:
    """依照模糊關鍵字產生較貼近主題的追問範例。"""
    keyword = query.strip() or "這個關鍵字"
    examples_by_topic = [
        (
            {"學士", "大學部", "學生"},
            [
                "學士班學生可以申請哪些獎助學金？",
                "學士班學生工讀時薪是多少？",
                "學士班學生請假規定是什麼？",
            ],
        ),
        (
            {"碩士", "博士", "研究生"},
            [
                "碩士班優秀新生獎勵的申請資格是什麼？",
                "研究生獎助學金怎麼分配？",
                "碩士生續領獎學金需要達到什麼條件？",
            ],
        ),
        (
            {"獎學金", "獎助學金", "補助", "獎勵"},
            [
                "端木愷校長獎學金的續領條件是什麼？",
                "研究生獎助學金怎麼分配？",
                "優秀應屆畢業生獎勵的選拔資格是什麼？",
            ],
        ),
        (
            {"請假", "假", "缺課"},
            [
                "期末考請假期限是多久？",
                "病假最晚要在什麼期限內辦理？",
                "請假需要送到哪個單位核准？",
            ],
        ),
        (
            {"宿舍", "住宿", "寢室"},
            [
                "校外宿舍可以隨意進入寢室檢查嗎？",
                "宿舍退宿或退費規定是什麼？",
                "宿舍輔導與管理人員有哪些職責？",
            ],
        ),
        (
            {"工讀", "時薪", "打工"},
            [
                "學生工讀時薪是多少？",
                "工讀助學金由哪個單位核發？",
                "申請工讀助學需要符合什麼條件？",
            ],
        ),
        (
            {"社團", "學生會", "會費"},
            [
                "社團成立需要符合什麼規定？",
                "學生會費如何代收？",
                "社團活動申請流程是什麼？",
            ],
        ),
    ]

    examples = [
        f"{keyword}相關規章的申請資格是什麼？",
        f"{keyword}相關規定的辦理流程是什麼？",
        f"{keyword}相關規定有哪些限制或條件？",
    ]
    for keywords, topic_examples in examples_by_topic:
        if any(k in keyword for k in keywords):
            examples = topic_examples
            break

    example_lines = "\n".join(f"- **{example}**" for example in examples)
    return (
        f"我目前只看到「{keyword}」這個較模糊的關鍵字，還不能判斷您要查哪一項規章。\n\n"
        "請把問題問得更具體一點，例如：\n"
        f"{example_lines}"
    )

def _is_leave_query(query: str) -> bool:
    return any(k in query.lower() for k in ["假", "leave", "absent", "vacation", "sick"])

def _build_system_prompt(user_query: str, sources: list) -> str:
    """建立 RAG 生成提示；只在請假問題加入請假專用規則，避免污染其他主題。"""
    source_list = "\n".join(f"- {source}" for source in sources) if sources else "- 無"
    leave_rules = ""
    if _is_leave_query(user_query):
        leave_rules = (
            "9. **嚴防期限與核定單位混淆**：不同假別（如「一般請假」與「學期考試請假」）的期限與核准單位分屬不同條文，**絕對不可混用**。請根據使用者所問的具體假別，找到該假別專屬的條文與期限進行回答：\n"
            "   - **一般請假（如事假、病假、生理假等）**：最遲應於缺課次日起**一週內**完成辦理。\n"
            "   - **學期考試（期末考）請假**：必須在考試結束後**五個工作日內**提出申請，由學系主任簽註意見並送**教務處**核定。\n"
            "   - 若使用者詢問期末考、學期考試或考試請假期限，第一個重點必須明確寫出：期限是**考試結束後五個工作日內**，且是工作日，不是一般自然日。\n"
        )
    format_rule_number = "10" if leave_rules else "9"

    return (
        "你是一位嚴謹的東吳大學（Soochow University, SCU）學生事務知識庫助手。請根據以下提供的 Context（法規或問答內容）精準回答使用者的問題。\n"
        "【嚴格要求】：\n"
        "1. **校名不可改寫**：所有回答都必須以**東吳大學**為主體。不得寫成 National Taiwan University、NTU、台大或其他學校；Context 沒有出現的校名一律不可加入。\n"
        "2. **必須使用繁體中文**：除非引用文件原文中的英文專有名詞，否則回答不可使用英文開場、英文標題或英文整段說明。\n"
        "3. **完全基於事實**：僅根據 Context 內有的內容回答。不可憑空想像、推論或加入外部知識。答案必須精準，不可過度推論。若 Context 中包含原則性規定（如「由委員會另訂之」、「以基本工資為原則」），請如實回答，不可回答找不到。\n"
        "4. **問題過於模糊時先反問**：若使用者只輸入單一關鍵字或 Context 中有多個可能主題，請先用繁體中文請使用者補充想查的具體事項，不要自行選一個主題長篇回答。\n"
        "5. **來源處理**：回答內文不要自行新增「來源：」、「參考文獻：」、「可用來源清單：」或頁碼段落；系統會在回答下方自動顯示來源標籤。若內文需要自然提及法規名稱，只能使用下方來源清單中的名稱，不可臆造來源。\n"
        "6. **條號處理**：不要自行猜測或改寫條號；只有在 Context 明確顯示同一段內容所屬條號時，才可提及條號。若不確定，直接摘要規定內容即可。\n"
        "7. **拒答處理**：若 Context 完全無關且找不到答案，請僅回答：「抱歉，在現有的企業知識庫中找不到與您問題相關的解答」，不准附帶其他多餘字句。\n"
        "8. **跨語言對照翻譯**：Context 若為英文，必須以中文作答。翻譯請使用台灣大專院校慣用語：\n"
        "   - Academic Affairs Office -> **教務處**\n"
        "   - Student Affairs Office -> **學務處**\n"
        "   - department chair -> **學系主任**\n"
        "   - semester examinations -> **學期考試（期末考）**\n"
        "   - temporary exams or midterms -> **臨時考試或期中考**\n"
        f"{leave_rules}"
        f"{format_rule_number}. **排版格式**：請務必使用 Markdown 格式回答。\n"
        "   - 第一段先用 1 句話直接回答問題，不要超過 40 個中文字。\n"
        "   - 若答案包含成員、資格、流程、期限、金額、條件或多個單位，必須使用 Markdown 條列 `- `，每個重點單獨一列；不要把「一、二、三」塞在同一段。\n"
        "   - 每個條列盡量不超過 45 個中文字；太長時請拆成多列。\n"
        "   - 每則回答至少標註 2 到 5 個重點。對於**允許/禁止、同意/不同意、例外情況、期限、分數、金額、資格、審核與核准單位、應辦事項、事後補件或報告**，必須使用雙星號標注。\n"
        "   - 若答案涉及是否可以做某事，必須把結論詞標粗，例如：**不可以**、**可以**、**不得**、**必須**。\n"
        "   - 若答案涉及獎學金、獎勵或續領，必須標粗**續領**、**學業成績平均**、**分數門檻**、**排名門檻**、**無懲處紀錄**等條件。\n"
        "   - 若答案涉及宿舍/檢查/隱私，必須標粗**未獲同意**、**不得隨意進入**、**特殊危急狀況**、**事後書面報告**等關鍵限制。\n"
        "   - 不要使用 Markdown 表格，表格在前端閱讀不穩定；請改用分段與條列。\n"
        "   - 不要輸出大段連續文字；若無法條列，至少分成短段落。\n\n"
        "可用來源清單（僅供核對，不要在回答末尾重複列出）：\n"
        f"{source_list}\n\n"
        "Context:\n"
        "{context}"
    )


ensure_data_directory()

_db = None

def _clear_runtime_caches(clear_db: bool = False):
    global _db
    if clear_db:
        _db = None
    reset_status_cache()
    reset_retrieval_caches()
    reset_repository_caches()

def init_vector_db(force_rebuild: bool = False, persist_directory: str | None = None):
    """初始化並建立向量資料庫，並在 PDF 檔案有變動時自動重建"""
    with _vector_db_lock:
        return _init_vector_db_locked(force_rebuild, persist_directory)


def _init_vector_db_locked(
    force_rebuild: bool = False,
    persist_directory: str | None = None,
):
    global _db
    chroma_dir = persist_directory or CHROMA_DIR

    # 檢查是否有 PDF 檔案
    pdf_files = _get_pdf_files()
    pdf_dir = _get_pdf_data_dir()
    
    # 記錄已加載的 PDF 列表的 meta 檔路徑
    meta_path = os.path.join(chroma_dir, "db_meta.json")
    
    need_rebuild = force_rebuild
    
    # 檢查資料庫是否存在
    if not need_rebuild:
        if not os.path.exists(chroma_dir) or len(os.listdir(chroma_dir)) == 0:
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
                
    if need_rebuild and not pdf_files:
        import shutil
        _clear_runtime_caches(clear_db=True)
        if os.path.exists(chroma_dir):
            shutil.rmtree(chroma_dir)
        return None

    # 如果需要重建且有 PDF 檔案，先刪除舊庫並重建
    if need_rebuild and pdf_files:
        print("🔄 偵測到 PDF 或 FAQ 檔案變動，正在重建向量資料庫...")
        import shutil
        _clear_runtime_caches(clear_db=True)
        if os.path.exists(chroma_dir):
            try:
                shutil.rmtree(chroma_dir)
            except Exception as e:
                print(f"⚠️ 刪除舊向量庫失敗: {e}，將嘗試直接覆蓋。")
            
        from langchain_community.document_loaders import PyPDFDirectoryLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        
        loader = PyPDFDirectoryLoader(pdf_dir)
        documents = loader.load()
        manifest_by_filename = {
            item.get("filename"): item
            for item in _load_managed_manifest().get("documents", [])
            if item.get("filename")
        }
        
        # 終極 PDF 編碼與 Ligature 合字清洗器，還原被破壞的英文單字，使地端 LLM 能正確閱讀理解
        for doc in documents:
            if doc.page_content:
                doc.page_content = _clean_pdf_text(doc.page_content)
            source_filename = os.path.basename(doc.metadata.get("source", ""))
            manifest_entry = manifest_by_filename.get(source_filename)
            if manifest_entry:
                doc.metadata["source_alias"] = manifest_entry.get("source_alias", "")
                doc.metadata["document_id"] = manifest_entry.get("document_id", "")
                doc.metadata["version_id"] = manifest_entry.get("version_id", "")
        
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
                for entry, managed_filename, source_alias in _iter_active_faq_entries():
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
                                    "source": os.path.join(pdf_dir, managed_filename),
                                    "source_alias": source_alias or source_name,
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
            persist_directory=chroma_dir
        )
        
        # 建立 meta 檔以記錄載入的檔案
        os.makedirs(chroma_dir, exist_ok=True)
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(_build_db_meta(pdf_files), f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"⚠️ 寫入 db_meta.json 失敗: {e}")
            
        _db = db
        return db
    
    # 如果不需要重建且資料庫存在，直接載入
    if os.path.exists(chroma_dir) and len(os.listdir(chroma_dir)) > 0:
        _db = Chroma(persist_directory=chroma_dir, embedding_function=get_embeddings())
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
    is_leave_query = _is_leave_query(user_query)
    
    # 為了節省算力與時間，非請假問題若長度大於 30 字，則直接返回不進行擴展
    if not is_leave_query and len(user_query.strip()) > 30:
        return _dedupe_queries(queries)
    
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
            return _dedupe_queries(queries)
        else:
            return _dedupe_queries(queries)
            
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
        
    return _dedupe_queries(queries)

def query_rag_stream(user_query: str, api_key: str = None, db = None, disable_expansion: bool = False):
    """查詢 RAG 系統並以生成器方式返回 metadata 與答案字元流 (支援 RRF 融合排序、查詢擴展與 Gemini API 備援)"""
    if _is_under_specified_query(user_query):
        yield {
            "type": "metadata",
            "sources": [],
            "detailed_sources": [],
            "engine_type": "需要補充問題",
            "expanded_queries": [user_query.strip()] if user_query.strip() else []
        }
        yield {
            "type": "content",
            "content": _build_clarification_message(user_query)
        }
        return

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
        is_leave_query = _is_leave_query(user_query)
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
            docs_sparse = _bm25_top_pdf_docs(bm25_pdf, pdf_texts, pdf_metadatas, tokenized_q, n=4)
            pdf_sparse_lists.append(docs_sparse)

            
    # 5. RRF 倒數排序融合與去重
    # 先對 PDF chunks 進行 RRF 融合
    merged_pdf_docs = rrf_fusion(pdf_dense_lists, pdf_sparse_lists, k=60)
    
    # 主題感知重排序：偵測到特定主題關鍵字時，將對應文件的 chunks 置頂
    # 原理：Dense 搜尋語義跨語言正確，但 BM25 因通用詞（如「辦理」）命中無關中文文件（如社團章程），
    # RRF 融合後可能將錯誤文件置於最終 context。此步驟在 RRF 後修正排序，確保主題對應文件優先。
    _priority_src = _detect_priority_source(user_query)
    if _priority_src:
        if not any(_doc_matches_source(d, _priority_src) for d in merged_pdf_docs):
            priority_docs = _priority_source_pdf_docs(bm25_index, user_query, _priority_src, n=4)
            if priority_docs:
                print(f"🎯 RRF 未命中主題文件，已從 {_priority_src} 補回 {len(priority_docs)} 個 chunks。")
                merged_pdf_docs = priority_docs + merged_pdf_docs

        _prio_docs = [d for d in merged_pdf_docs if _doc_matches_source(d, _priority_src)]
        _other_docs = [d for d in merged_pdf_docs if not _doc_matches_source(d, _priority_src)]
        merged_pdf_docs = _prio_docs + _other_docs
    
    pdf_docs = _dedupe_documents_by_identity(merged_pdf_docs, limit=4)  # 取前 4 個最相關法規 chunk
    
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
    docs = _dedupe_documents_by_identity(faq_docs_result + pdf_docs)
    
    # 主題感知淨化過濾器：若偵測到特定主題文件，且檢索結果中包含此文件，則精準排除無關文件，避免地端模型混淆
    if _priority_src:
        purified_docs = [d for d in docs if _doc_matches_source(d, _priority_src)]
        if purified_docs:
            docs = _dedupe_documents_by_identity(purified_docs)
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
    system_prompt = _build_system_prompt(user_query, sources)
    
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
    return _get_full_system_status(check_vector_db_status)
