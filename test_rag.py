import sys
import os
import requests

# 確保 python 能定位到同目錄的 backend 模組
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from backend.services.rag_service import ensure_ollama_running, query_rag
from backend.config import get_settings

def test_rag_pdf_retrieval():
    print("=== 測試: 地端 PDF 知識庫 RAG 檢索與 LLM 推論 ===")
    
    # 嘗試自動啟動 Ollama
    ensure_ollama_running()
    
    # 檢查 Ollama 是否在運作
    ollama_url = get_settings().ollama_base_url
    try:
        response = requests.get(ollama_url, timeout=3)
        ollama_running = (response.status_code == 200)
    except Exception:
        ollama_running = False
        
    if not ollama_running:
        print(f"⚠️ 偵測到地端 Ollama ({ollama_url}) 未啟動，無法進行實際推論測試。")
        print("（請確保已執行 'ollama run gemma3' 且已下載 'nomic-embed-text' 嵌入模型）")
        return
        
    print("地端 Ollama 運作中，開始檢索本地 PDF 檔案...")
    
    # 測試提問
    query = "工讀時薪是多少？"

    print(f"問題: {query}")
    
    result = query_rag(user_query=query)
    
    print("\n[RAG 系統回答]:")
    print(result["answer"])
    print("\n[資料來源]:")
    print(result["sources"])
    
    assert len(result["answer"]) > 0, "回答不應為空"
    # 如果有 sources，印出確認
    if result["sources"]:
        print("-> PDF RAG 整合測試通過！\n")
    else:
        print("⚠️ 注意：成功從 Ollama 取得回答，但未能從資料庫檢索到 PDF 來源。請確認 data/ 目錄下是否有 PDF 文件。")

if __name__ == "__main__":
    try:
        test_rag_pdf_retrieval()
        print("🎉 地端 PDF RAG 功能測試完成！")
    except AssertionError as e:
        print(f"❌ 測試失敗: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"💥 發生未預期錯誤: {e}")
        sys.exit(1)
