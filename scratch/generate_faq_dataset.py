"""
FAQ 自動訓練腳本（全庫版）
================================================
功能：
  - 讀取 data/ 下所有 PDF，切分成細粒度 chunk（400 字）
  - 對每個 chunk 呼叫 Gemini API 生成 8 個多角度、口語化的 FAQ 問題
  - 增量式更新：已有快取的 chunk 直接跳過，不重複呼叫 API
  - 自動合併既有手動標注的 faq_cache.json，不覆蓋人工條目
  - 生成完成後輸出統計報告

使用方式：
  cd /path/to/project
  python scratch/generate_faq_dataset.py

完成後請在 Streamlit 側邊欄點擊「立即更新/訓練知識庫」以重建向量資料庫。
"""

import os
import sys
import json
import hashlib
import time

# 確保從專案根目錄執行
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

DATA_DIR = "data"
FAQ_CACHE_PATH = os.path.join(DATA_DIR, "faq_cache.json")
TITLE_MAPPING_PATH = os.path.join("backend", "services", "title_mapping.json")

# ─── 讀取 Gemini API 金鑰 ─────────────────────────────────────────────────────
gemini_key = None
env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                if k.strip() == "GEMINI_API_KEY":
                    gemini_key = v.strip().strip("'").strip('"')

# ─── 輔助函數 ─────────────────────────────────────────────────────────────────
def get_md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def generate_faqs_with_llm(chunk_text: str, doc_title: str, api_key: str = None, num_questions: int = 5) -> list:
    """
    呼叫 LLM 針對法規文本片段生成指定數量的多角度口語化 FAQ 問題。
    支援 Gemini API（優先）與地端 Ollama（降級）。
    """
    prompt = (
        f"你是一位熟悉東吳大學各項法規的學生諮詢助手。\n"
        f"現在有一段來自「{doc_title}」的法規內容，請根據這段內容，"
        f"生成 {num_questions} 個學生在日常生活中可能會問的「口語化、日常、自然」的問題。\n\n"
        "《生成要求》：\n"
        "1. 每個問題都必須能被這段法規內容完整回答，不可超出範圍。\n"
        f"2. 請生成共 {num_questions} 個多角度的問題（包含直覺口語、時間期限/金額/次數等數字邊界條件、申辦流程/單位/文件、假設情境「如果我....」、通俗俗稱等）。\n"
        "3. 禁止提及與本段法規內容完全無關的主題。\n"
        f"4. 只輸出這 {num_questions} 個問題，每行一個，不要加序號、引號或任何解釋文字。\n\n"
        f"法規內容：\n{chunk_text}"
    )

    # 優先呼叫 Gemini API
    if api_key:
        for attempt in range(2):
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_name="gemini-2.5-flash")
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.6, "max_output_tokens": 512}
                )
                lines = [l.strip() for l in response.text.split("\n") if l.strip()]
                cleaned = []
                for l in lines:
                    c = l.lstrip("0123456789.①②③④⑤⑥⑦⑧⑨⑩-*•） ").strip().strip('"').strip("'")
                    if c and len(c) > 5:
                        cleaned.append(c)
                if len(cleaned) >= 3:
                    return cleaned[:num_questions]
                # 呼叫成功但問題數不足，代表內容太貧乏（例如只有修訂日期），不需重試，直接跳過
                print(f"   ⚠️ 回傳問題數不足（{len(cleaned)} 題），代表該片段內容過短或無實質法規，跳過該片段。", flush=True)
                return []
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                    if attempt == 0:
                        print("   ⚠️ Gemini API 速率限制，等待 3 秒後嘗試最後一次...", flush=True)
                        time.sleep(3)
                    else:
                        print("   ⚠️ Gemini API 額度已用滿，自動切換至地端 gemma3 模型生成...", flush=True)
                        break
                else:
                    if attempt == 0:
                        print(f"   ⚠️ Gemini API 出錯: {e}，等待 3 秒後重試...", flush=True)
                        time.sleep(3)
                    else:
                        print(f"   ⚠️ Gemini API 連續出錯，自動降級至地端 gemma3 生成...", flush=True)
                        break

    # 降級至地端 Ollama (gemma3)
    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage
        llm = ChatOllama(model="gemma3", base_url="http://localhost:11434", temperature=0.6)
        response = llm.invoke([HumanMessage(content=prompt)])
        lines = [l.strip() for l in response.content.split("\n") if l.strip()]
        cleaned = []
        for l in lines:
            c = l.lstrip("0123456789.①②③④⑤⑥⑦⑧⑨⑩-*•） ").strip().strip('"').strip("'")
            if c and len(c) > 5:
                cleaned.append(c)
        return cleaned[:num_questions]
    except Exception as e:
        # 如果地端沒開，且 API 也失敗了，不再重複報錯
        pass
    return []


# ─── 主程式 ───────────────────────────────────────────────────────────────────
def main():
    print("=" * 60, flush=True)
    print("🚀 FAQ 全庫自動訓練腳本啟動", flush=True)
    print("=" * 60, flush=True)

    if gemini_key:
        print("✅ 已偵測到 Gemini API 金鑰，將使用雲端 API 加速生成", flush=True)
    else:
        print("⚠️  未偵測到 Gemini API 金鑰，將使用地端 Ollama 生成（速度較慢）", flush=True)
    print(flush=True)

    # ── 1. 載入並切分所有 PDF ─────────────────────────────────────────────────
    pdf_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".pdf")] if os.path.exists(DATA_DIR) else []
    if not pdf_files:
        print("❌ data/ 資料夾中沒有任何 PDF 檔案，請先放入法規 PDF 後再執行。", flush=True)
        return

    print(f"📚 找到 {len(pdf_files)} 個 PDF 檔案，開始讀取與切分...", flush=True)

    from langchain_community.document_loaders import PyPDFDirectoryLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    loader = PyPDFDirectoryLoader(DATA_DIR)
    documents = loader.load()

    # 終極 PDF 編碼與 Ligature 合字清洗器，還原被破壞的英文單字
    for doc in documents:
        if doc.page_content:
            doc.page_content = doc.page_content.replace('\u014c', 'ft')  # Ō -> ft (after)
            doc.page_content = doc.page_content.replace('\u019f', 'ti')  # Ɵ -> ti (national)
            doc.page_content = doc.page_content.replace('\u01a9', 'tt')  # Ʃ -> tt (attend)
            doc.page_content = doc.page_content.replace('\ufb00', 'ff')  # ﬀ -> ff
            doc.page_content = doc.page_content.replace('\ufb01', 'fi')  # ﬁ -> fi
            doc.page_content = doc.page_content.replace('\ufb02', 'fl')  # ﬂ -> fl
            doc.page_content = doc.page_content.replace('\ufb03', 'ffi') # ﬃ -> ffi

    # 定向增量 FAQ 訓練名單（擴增到 700 筆目標）
    targeted_files = {
        "6800ade9ad279805632161.pdf",  # 東吳大學學生請假規則
        "6261123f68ff3747511986.pdf",  # 東吳大學學生工讀助學實施辦法
        "6418115967cf9033858547.pdf",  # 東吳大學校外學生宿舍輔導及管理辦法
        "6228681d46e33141989956.pdf",  # 東吳大學學生銷過實施辦法
        "6926c31472b20396768425.pdf"   # 東吳大學端木愷校長獎學金實施要點
    }

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=80)
    chunks = text_splitter.split_documents(documents)
    print(f"✂️  切分完成，共 {len(chunks)} 個文本片段", flush=True)
    print(flush=True)

    # ── 2. 載入標題映射 ───────────────────────────────────────────────────────
    title_mapping = {}
    if os.path.exists(TITLE_MAPPING_PATH):
        try:
            with open(TITLE_MAPPING_PATH, 'r', encoding='utf-8') as f:
                title_mapping = json.load(f)
        except Exception:
            pass

    # ── 3. 載入現有快取（增量合併，不覆蓋人工條目）────────────────────────────
    faq_cache = {}
    if os.path.exists(FAQ_CACHE_PATH):
        try:
            with open(FAQ_CACHE_PATH, "r", encoding="utf-8") as f:
                faq_cache = json.load(f)
            print(f"📂 已載入既有快取：{len(faq_cache)} 筆紀錄（含人工標注）", flush=True)
        except Exception as e:
            print(f"⚠️  載入快取失敗，將從零開始: {e}", flush=True)

    # ── 4. 逐一處理每個 Chunk ─────────────────────────────────────────────────
    new_cache = {}
    skipped = 0
    generated = 0
    failed = 0
    total_to_process = 0

    # 先統計需要處理的數量
    for chunk in chunks:
        chunk_text = chunk.page_content.strip()
        if len(chunk_text) < 30:
            continue
        src = chunk.metadata.get("source", "")
        source_name = os.path.basename(src)
        chunk_hash = get_md5(chunk_text)
        
        is_target = source_name in targeted_files
        existing_faqs = faq_cache.get(chunk_hash, {}).get("faqs", [])
        
        # 若是重點檔案且現存題數小於 10 題，需要處理
        if not (chunk_hash in faq_cache and existing_faqs and (not is_target or len(existing_faqs) >= 10)):
            total_to_process += 1

    print(f"🔍 需要生成 FAQ 的新 Chunk 數：{total_to_process} 個（已快取的將直接跳過）", flush=True)
    print(flush=True)

    for idx, chunk in enumerate(chunks):
        chunk_text = chunk.page_content.strip()
        if len(chunk_text) < 30:
            continue

        src = chunk.metadata.get("source", "")
        source_name = os.path.basename(src)
        friendly_title = title_mapping.get(source_name, source_name.replace(".pdf", ""))
        page = chunk.metadata.get("page", 0) + 1
        chunk_hash = get_md5(chunk_text)

        # 已有快取，且不是重點檔案，或重點檔案題數已大於等於 10 個時，直接保留
        is_target = source_name in targeted_files
        existing_faqs = faq_cache.get(chunk_hash, {}).get("faqs", [])
        
        if chunk_hash in faq_cache and existing_faqs and (not is_target or len(existing_faqs) >= 10):
            new_cache[chunk_hash] = faq_cache[chunk_hash]
            skipped += 1
            continue

        # 生成新 FAQ
        progress = generated + failed + 1
        print(f"[{progress}/{total_to_process}] 📄 {friendly_title} (第 {page} 頁)", flush=True)
        print(f"   內容預覽: {chunk_text[:80].strip()}...", flush=True)

        num_questions = 10 if is_target else 5
        faqs = generate_faqs_with_llm(chunk_text, friendly_title, gemini_key, num_questions=num_questions)

        if faqs:
            print(f"   ✅ 生成 {len(faqs)} 個口語問題", flush=True)
            for q in faqs:
                print(f"      - {q}", flush=True)
            new_cache[chunk_hash] = {
                "source": source_name,
                "page": page,
                "content": chunk_text,
                "faqs": faqs
            }
            generated += 1
        else:
            print("   ❌ 生成失敗，跳過", flush=True)
            failed += 1

        # 每 5 筆寫入一次（防止中途中斷損失）
        if (generated + failed) % 5 == 0:
            merged = {**faq_cache, **new_cache}
            with open(FAQ_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=4)
            print(f"   💾 中途存檔完成（目前共 {len(merged)} 檔條目）", flush=True)

        # API 速率限制保護，每次主動延遲 4.5 秒（相當於限制 RPM <= 13），預防觸發免費 Key 的 15 RPM 速率限制
        if gemini_key:
            time.sleep(4.5)
        else:
            time.sleep(0.5)

        print(flush=True)

    # ── 5. 最終合併存檔（保留所有人工條目 + 既有快取）────────────────────────
    final_cache = {**faq_cache, **new_cache}
    with open(FAQ_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(final_cache, f, ensure_ascii=False, indent=4)

    # ── 6. 統計報告 ───────────────────────────────────────────────────────────
    total_faq_questions = sum(len(v.get("faqs", [])) for v in final_cache.values())
    print("=" * 60)
    print("🎉 FAQ 全庫自動訓練完成！")
    print("=" * 60)
    print(f"  📦 既有快取跳過：{skipped} 個 chunk")
    print(f"  ✅ 新生成：{generated} 個 chunk")
    print(f"  ❌ 生成失敗：{failed} 個 chunk")
    print(f"  📊 FAQ 快取總條目：{len(final_cache)} 個 chunk")
    print(f"  💬 口語 FAQ 問題總數：{total_faq_questions} 個")
    print()
    print("📌 下一步：請在 Streamlit 側邊欄點擊「🔄 立即更新/訓練知識庫」")
    print("   （或執行：python -c \"from backend.services.rag_service import init_vector_db; init_vector_db(force_rebuild=True)\"）")
    print("=" * 60)


if __name__ == "__main__":
    main()
