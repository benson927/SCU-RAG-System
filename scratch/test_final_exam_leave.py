import sys
import os

# 將專案根目錄與 backend 目錄加入 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.services.rag_service import query_rag

# 讀取 .env 中的 API KEY
gemini_key = None
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                if k.strip() == "GEMINI_API_KEY":
                    gemini_key = v.strip().strip("'").strip('"')

query = "如果是期末考（學期考試）缺考想要申請請假，最晚必須在考試結束後的幾天內提出申請？要送去哪個單位審核？"

def test_mode(api_key=None, mode_name="地端模式"):
    print(f"\n=== 測試 {mode_name} ===")
    result = query_rag(query, api_key=api_key)
    
    print(f"推論引擎: {result['engine_type']}")
    print(f"回答內容:\n{result['answer']}")
    print(f"來源資料: {result['sources']}")
    
    # 驗證是否檢索到英文學生請假規則
    found_leave_regs = any("Leave" in src for src in result['sources'])
    assert found_leave_regs, "❌ 失敗：未檢索到 Student Leave Regulations！"
    print("✅ 成功檢索到 Student Leave Regulations！")
    
    # 驗證答案的準確度
    # 英文請假規則中：五個工作天內 (five working days)，教務處核定 (Academic Affairs Office)
    answer_text = result['answer'].lower()
    has_five = any(k in answer_text for k in ["5", "五", "five"])
    has_dept = any(k in answer_text for k in ["教務處", "學務處", "學業事務", "學術事務", "academic affairs"])
    
    if not has_five:
        print("❌ 失敗：回答中未提及 '5' 天或 '五' 天！")
    else:
        print("✅ 成功提及期限（5 天）！")
        
    if not has_dept:
        print("❌ 失敗：回答中未提及教務處或學務處！")
    else:
        print("✅ 成功提及審核單位！")
        
    print(f"-> {mode_name} 測試完成！")

if __name__ == "__main__":
    # 1. 測試地端模式
    try:
        test_mode(api_key=None, mode_name="純地端模式 🦉")
    except Exception as e:
        print(f"純地端模式測試出錯: {e}")
        
    # 2. 測試 API 加速模式 (若有金鑰)
    if gemini_key:
        try:
            test_mode(api_key=gemini_key, mode_name="API 加速模式 ⚡")
        except Exception as e:
            print(f"API 加速模式測試出錯: {e}")
    else:
        print("\n⚠️ 未在 .env 中發現 GEMINI_API_KEY，跳過 API 加速模式測試。")
