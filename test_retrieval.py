import sys
import os

# 將專案根目錄與 backend 目錄加入 sys.path 以利導入
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from backend.services.rag_service import query_rag

def test_chinese_retrieval_and_boosting():
    print("=== 測試 1: 本地中文檢索與 Boosting (工讀時薪) ===")
    query = "工讀時薪是多少？"
    result = query_rag(query)
    
    assert result is not None, "回傳結果不應為 None"
    print(f"推論引擎: {result['engine_type']}")
    print(f"回答內容:\n{result['answer']}")
    print(f"來源資料: {result['sources']}")
    
    # 驗證是否檢索到相關法規
    assert len(result['detailed_sources']) > 0, "應至少檢索到一筆參考來源"
    found = any("工讀" in src['title'] or "工讀" in src['content'] for src in result['detailed_sources'])
    assert found, "檢索到的條文或回答中應包含工讀相關的內容"
    print("-> 測試 1 通過！\n")

def test_cross_language_retrieval():
    print("=== 測試 2: 中英跨語言語意增強 (學生請假規則) ===")
    query = "請問心理調適假可以請幾天？"
    result = query_rag(query)
    
    assert result is not None, "回傳結果不應為 None"
    print(f"推論引擎: {result['engine_type']}")
    print(f"回答內容:\n{result['answer']}")
    print(f"來源資料: {result['sources']}")
    
    assert len(result['detailed_sources']) > 0, "應至少檢索到一筆參考來源"
    found = any("Leave" in src['title'] or "Regula" in src['title'] for src in result['detailed_sources'])
    assert found, "檢索到的條文應來自於英文學生請假規則 (Leave Regulations)"
    print("-> 測試 2 通過！\n")

def test_no_match_safety_valve():
    print("=== 測試 3: 無匹配安全閥 (防幻覺過濾) ===")
    query = "今天晚餐要吃什麼好呢？"
    result = query_rag(query)
    
    assert result is not None, "回傳結果不應為 None"
    print(f"推論引擎: {result['engine_type']}")
    print(f"回答內容:\n{result['answer']}")
    
    # 驗證防幻覺機制是否發揮作用 (LLM 應指出在 Context 中找不到答案)
    assert "找不到" in result['answer'] or "抱歉" in result['answer'] or "無法回答" in result['answer'], "對於無關提問，LLM 應拒絕回答以防止幻覺"
    print("-> 測試 3 通過！\n")

def test_dormitory_inspection():
    print("=== 測試 4: 宿舍隱私與檢查規則 ===")
    query = "校外宿舍可以隨意進入寢室檢查嗎？"
    result = query_rag(query)
    
    assert result is not None, "回傳結果不應為 None"
    print(f"推論引擎: {result['engine_type']}")
    print(f"回答內容:\n{result['answer']}")
    print(f"來源資料: {result['sources']}")
    
    assert len(result['detailed_sources']) > 0, "應至少檢索到一筆參考來源"
    found = any("宿舍" in src['title'] or "宿舍" in src['content'] or "檢查" in src['content'] for src in result['detailed_sources'])
    assert found, "檢索到的條文中應包含宿舍管理相關的內容"
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
