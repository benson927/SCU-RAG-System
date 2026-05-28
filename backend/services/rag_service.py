import os
import json
import jieba
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate

DATA_DIR = "data"
CHROMA_DIR = "chroma_db"

# 確保 PDF 目錄存在
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# 初始化地端嵌入模型
# 使用 Ollama 的 nomic-embed-text，此模型專為文本嵌入設計，適合地端高效執行。
embeddings = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://localhost:11434"
)

# 初始化地端 LLM 引擎 (使用 gemma3)
llm = ChatOllama(
    model="gemma3",
    base_url="http://localhost:11434",
    temperature=0.0  # 設為 0 以獲得最穩定、不隨機且不產生幻覺的回答
)

def init_vector_db():
    """初始化並建立向量資料庫，並在 PDF 檔案有變動時自動重建"""
    # 檢查是否有 PDF 檔案
    pdf_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".pdf")]) if os.path.exists(DATA_DIR) else []
    
    # 記錄已加載的 PDF 列表的 meta 檔路徑
    meta_path = os.path.join(CHROMA_DIR, "db_meta.json")
    
    need_rebuild = False
    
    # 檢查資料庫是否存在
    if not os.path.exists(CHROMA_DIR) or len(os.listdir(CHROMA_DIR)) == 0:
        need_rebuild = True
    else:
        # 檢查 meta 檔
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    db_meta = json.load(f)
                loaded_files = db_meta.get("files", [])
                # 如果檔案列表不一致，需要重建
                if loaded_files != pdf_files:
                    need_rebuild = True
            except Exception:
                need_rebuild = True
        else:
            need_rebuild = True
            
    # 如果需要重建且有 PDF 檔案，先刪除舊庫並重建
    if need_rebuild and pdf_files:
        print("🔄 偵測到 PDF 檔案變動，正在重建向量資料庫...")
        import shutil
        if os.path.exists(CHROMA_DIR):
            try:
                shutil.rmtree(CHROMA_DIR)
            except Exception as e:
                print(f"⚠️ 刪除舊向量庫失敗: {e}，將嘗試直接覆蓋。")
            
        from langchain_community.document_loaders import PyPDFDirectoryLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        
        loader = PyPDFDirectoryLoader(DATA_DIR)
        documents = loader.load()
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        chunks = text_splitter.split_documents(documents)
        
        db = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=CHROMA_DIR
        )
        
        # 建立 meta 檔以記錄載入的檔案
        os.makedirs(CHROMA_DIR, exist_ok=True)
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({"files": pdf_files}, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"⚠️ 寫入 db_meta.json 失敗: {e}")
            
        return db
    
    # 如果不需要重建且資料庫存在，直接載入
    if os.path.exists(CHROMA_DIR) and len(os.listdir(CHROMA_DIR)) > 0:
        return Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    
    return None

def generate_expanded_queries(user_query: str, api_key: str = None) -> list:
    """利用 LLM 將使用者查詢擴展為多個檢索句"""
    queries = [user_query]
    
    # 只有當查詢較短時才需要進行擴展以節省時間與算力
    if len(user_query.strip()) > 10:
        return queries
        
    prompt = (
        f"請將使用者的簡短搜尋詞「{user_query}」擴展為 3 個適合法規與文件檢索的完整中文搜尋句子或關鍵字組合。\n"
        "【要求】：\n"
        "1. 必須與原詞高度相關，適合用來在法規庫中進行語意或關鍵字搜尋。\n"
        "2. 僅輸出這 3 個擴展後的搜尋句，每行一個，前面不要加上序號、引號或任何多餘的解釋文字。\n"
    )
    
    try:
        if api_key:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name="gemini-1.5-flash")
            response = model.generate_content(prompt, generation_config={"temperature": 0.2})
            text = response.text
        else:
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=prompt)])
            text = response.content
            
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

def query_rag(user_query: str, api_key: str = None) -> dict:
    """查詢 RAG 系統並返回答案與來源 (支援 RRF 融合排序、查詢擴展與 Gemini API 備援)"""
    # 1. 檢索本地向量資料庫（PDF 知識庫）
    db = init_vector_db()
    
    if db is None:
        return {
            "answer": "抱煙，目前系統知識庫為空。請先在 `data/` 資料夾下放入 PDF 檔案以建立知識庫。",
            "sources": [],
            "detailed_sources": [],
            "engine_type": "未啟動"
        }
        
    # 2. 進行查詢擴展
    queries = generate_expanded_queries(user_query, api_key)
    
    dense_lists = []
    sparse_lists = []
    
    # 3. 準備 BM25 語料庫
    all_data = db.get()
    all_texts = all_data["documents"]
    all_metadatas = all_data["metadatas"]
    
    if all_texts:
        tokenized_corpus = [list(jieba.cut(doc)) for doc in all_texts]
        bm25 = BM25Okapi(tokenized_corpus)
    else:
        bm25 = None
        
    # 4. 多重查詢檢索
    for q in queries:
        # 向量檢索 (Chroma)
        docs_dense = db.similarity_search(q, k=4)
        dense_lists.append(docs_dense)
        
        # 關鍵字檢索 (BM25)
        if bm25 and all_texts:
            tokenized_q = list(jieba.cut(q))
            scores = bm25.get_scores(tokenized_q)
            top_n_idx = bm25.get_top_n(tokenized_q, range(len(all_texts)), n=4)
            docs_sparse = []
            for idx in top_n_idx:
                if scores[idx] > 0:
                    docs_sparse.append(Document(page_content=all_texts[idx], metadata=all_metadatas[idx]))
            sparse_lists.append(docs_sparse)
            
    # 5. RRF 倒數排序融合與去重
    merged_docs = rrf_fusion(dense_lists, sparse_lists, k=60)
    docs = merged_docs[:4]  # 僅取出前 4 個最相關的片段送給 LLM
    
    if not docs:
        return {
            "answer": "抱歉，從現有法規中找不到與您問題相關的解答。",
            "sources": [],
            "detailed_sources": [],
            "engine_type": "地端模式 🦉"
        }
        
    # 載入檔名與真實標題的映射
    mapping_path = os.path.join(os.path.dirname(__file__), 'title_mapping.json')
    title_mapping = {}
    if os.path.exists(mapping_path):
        with open(mapping_path, 'r', encoding='utf-8') as f:
            title_mapping = json.load(f)
            
    # 合併檢索到的 context 文字與資訊來源
    context_parts = []
    sources = []
    detailed_sources = []
    
    for doc in docs:
        src = doc.metadata.get("source", "未知來源")
        source_name = os.path.basename(src)
        page = doc.metadata.get("page", 0) + 1  # LangChain page 索引從 0 開始
        
        friendly_title = title_mapping.get(source_name, source_name)
            
        context_parts.append(f"[來源檔案: {friendly_title} (第 {page} 頁)]\n{doc.page_content}")
        
        source_info = f"{friendly_title} (第 {page} 頁)"
        if source_info not in sources:
            sources.append(source_info)
            
        detailed_sources.append({
            "title": source_info,
            "content": doc.page_content
        })
            
    context_text = "\n\n".join(context_parts)
    
    # 6. 設計地端 RAG Prompt
    system_prompt = (
        "你是一位嚴謹的企業內部知識庫助手。請根據以下提供的 Context（檢索到的法規或文檔內容）回答使用者的問題。\n"
        "【嚴格要求】：\n"
        "1. 僅根據 Context 內有的事實進行回答。如果 Context 內容不足以回答該問題，請直接說：「抱歉，在現有的企業知識庫中找不到與您問題相關的解答」，切勿憑空想像或加入外部知識。\n"
        "2. 所有的回覆與說明必須使用中文。\n"
        "3. 答案必須精準，不可有胡亂編造或推論過度的情況，並在回答中提及你的參考資料來源（檔名與頁數）。\n"
        "4. 【簡短關鍵字特別處理】：如果使用者輸入的是簡短的關鍵字或名詞（例如「繁星」、「時薪」等），而非完整問題，請將 Context 中所有提及該關鍵字的法規規定、獎勵、標準等內容整理並詳細列出，不可以說找不到。\n"
        "5. 【排版要求】：請使用 Markdown 格式讓答案更易讀。請適當地使用條列式（Bullet points）、針對關鍵數字或重點項目使用**粗體**，並且適當分段。\n\n"
        "Context:\n"
        "{context}"
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}")
    ])
    
    # 7. 呼叫 LLM 進行生成（包含 Gemini API 與地端 Ollama 備援降級邏輯）
    answer_text = None
    engine_type = "地端模式 🦉"
    
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
                model_name="gemini-1.5-flash",
                system_instruction=system_prompt.replace("{context}", context_text)
            )
            response = model.generate_content(
                user_query,
                generation_config={"temperature": 0.0},
                safety_settings=safety_settings
            )
            answer_text = response.text
            engine_type = "API 加速模式 ⚡"
        except Exception as e:
            print(f"⚠️ Gemini API 調用失敗，將自動降級至地端 Ollama: {e}")
            
    if not answer_text:
        # 呼叫地端 Ollama
        formatted_prompt = prompt.invoke({"context": context_text, "input": user_query})
        response = llm.invoke(formatted_prompt)
        answer_text = response.content
        engine_type = "地端模式 🦉"
            
    return {
        "answer": answer_text,
        "sources": sources,
        "detailed_sources": detailed_sources,
        "engine_type": engine_type
    }
