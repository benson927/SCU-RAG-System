import sys
from unittest.mock import MagicMock

# 1. 建立假的 streamlit 模組以避免導入 app.py 時發生 runtime 錯誤
class MockSessionState(dict):
    def __getattr__(self, name):
        return self.get(name)
    def __setattr__(self, name, value):
        self[name] = value

class MockStreamlit:
    def __init__(self):
        self.session_state = MockSessionState()

    def cache_resource(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def decorator(func):
            return func
        return decorator
    
    def cache_data(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def decorator(func):
            return func
        return decorator

    def columns(self, spec, *args, **kwargs):
        if isinstance(spec, int):
            num = spec
        elif isinstance(spec, (list, tuple)):
            num = len(spec)
        else:
            num = 2
        return [MagicMock() for _ in range(num)]

    def chat_input(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        return MagicMock()

sys.modules['streamlit'] = MockStreamlit()

# 直接導入同目錄底下的 app
import app

def test_chinese_retrieval_and_boosting():
    print("=== 測試 1: 本地中文檢索與 Boosting (工讀時薪) ===")
    query = "工讀時薪是多少？"
    all_chunks = app.chunk_documents(app.RAW_DOCUMENTS)
    vectorizer, tfidf_matrix = app.build_search_index(all_chunks)
    
    results = app.retrieve_relevant_chunks(query, vectorizer, tfidf_matrix, all_chunks, top_k=3)
    
    assert len(results) > 0, "應檢索到結果"
    top_doc = results[0]
    print(f"Top 1 文件 ID: {top_doc['doc_id']}, 標題: {top_doc['title']}, 相似度分數: {top_doc['score']:.4f}")
    assert top_doc['doc_id'] == "文件十二", "最相關的文件應為文件十二"
    
    summary = app.extract_answer_summary(query, results)
    print(f"提取之答案摘要:\n{summary}")
    assert "法定基本時薪" in summary or "時薪" in summary, "摘要中應提及時薪相關說明"
    print("-> 測試 1 通過！\n")

def test_cross_language_retrieval():
    print("=== 測試 2: 中英跨語言語意增強 (心理調適假) ===")
    query = "請問心理調適假可以請幾天？"
    all_chunks = app.chunk_documents(app.RAW_DOCUMENTS)
    vectorizer, tfidf_matrix = app.build_search_index(all_chunks)
    
    results = app.retrieve_relevant_chunks(query, vectorizer, tfidf_matrix, all_chunks, top_k=3)
    
    assert len(results) > 0, "應檢索到結果"
    top_doc = results[0]
    print(f"Top 1 文件 ID: {top_doc['doc_id']}, 標題: {top_doc['title']}, 相似度分數: {top_doc['score']:.4f}")
    assert top_doc['doc_id'] == "文件七", "最相關的文件應為文件七"
    
    summary = app.extract_answer_summary(query, results)
    print(f"提取之答案摘要:\n{summary}")
    assert "Psychological Adjustment Leave" in top_doc['content'] or "Psychological" in top_doc['content'], "文件內容應包含英文對應條款"
    print("-> 測試 2 通過！\n")

def test_no_match_safety_valve():
    print("=== 測試 3: 無匹配安全閥 (低相似度過濾) ===")
    query = "今天晚餐要吃什麼好呢？"
    all_chunks = app.chunk_documents(app.RAW_DOCUMENTS)
    vectorizer, tfidf_matrix = app.build_search_index(all_chunks)
    
    results = app.retrieve_relevant_chunks(query, vectorizer, tfidf_matrix, all_chunks, top_k=3)
    
    print(f"檢索到的結果數量: {len(results)}")
    for r in results:
        print(f"文件: {r['doc_id']}, 分數: {r['score']:.4f}")
    assert len(results) == 0, "對於無關提問，結果應為空（被安全閥過濾）"
    print("-> 測試 3 通過！\n")

def test_dormitory_inspection():
    print("=== 測試 4: 宿舍隱私與檢查規則 ===")
    query = "校外宿舍可以隨意進入寢室檢查嗎？"
    all_chunks = app.chunk_documents(app.RAW_DOCUMENTS)
    vectorizer, tfidf_matrix = app.build_search_index(all_chunks)
    
    results = app.retrieve_relevant_chunks(query, vectorizer, tfidf_matrix, all_chunks, top_k=3)
    
    assert len(results) > 0, "應檢索到結果"
    top_doc = results[0]
    print(f"Top 1 文件 ID: {top_doc['doc_id']}, 標題: {top_doc['title']}, 相似度分數: {top_doc['score']:.4f}")
    assert top_doc['doc_id'] == "文件十一", "最相關的文件應為文件十一"
    
    summary = app.extract_answer_summary(query, results)
    print(f"提取之答案摘要:\n{summary}")
    
    found = any("未經同意" in r['content'] or "進入寢室" in r['content'] or "檢查" in r['content'] for r in results)
    assert found, "檢索到的結果 chunks 中應包含宿舍檢查規定"
    print("-> 測試 4 通過！\n")

if __name__ == "__main__":
    try:
        test_chinese_retrieval_and_boosting()
        test_cross_language_retrieval()
        test_no_match_safety_valve()
        test_dormitory_inspection()
        print("🎉 所有功能測試全部通過！")
    except AssertionError as e:
        print(f"❌ 測試失敗: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"💥 發生未預期錯誤: {e}")
        sys.exit(1)
