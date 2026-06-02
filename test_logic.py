import unittest
import sys
import os

# 確保後端目錄在 Python Path 中以利載入 backend 模組
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.append(_CURRENT_DIR)

from backend.services.rag_service import _detect_priority_source, rrf_fusion, get_full_system_status
from langchain_core.documents import Document

class TestRAGPureLogic(unittest.TestCase):
    """測試 RAG 系統中不需外部 API (如 Ollama/Gemini) 的純邏輯函數"""

    def test_topic_priority_source_detection(self):
        """測試關鍵字主題感知偵測器，確保不同詞彙能精確匹配對應法規"""
        # 測試「請假」相關字眼
        self.assertEqual(_detect_priority_source("我下學期想請假"), "6800ade9ad279805632161.pdf")
        self.assertEqual(_detect_priority_source("缺課太多會怎樣嗎"), "6800ade9ad279805632161.pdf")
        
        # 測試「工讀」相關字眼
        self.assertEqual(_detect_priority_source("工讀時薪是多少"), "6261123f68ff3747511986.pdf")
        
        # 測試「宿舍」相關字眼
        self.assertEqual(_detect_priority_source("我想申請宿舍退費"), "6418115967cf9033858547.pdf")
        
        # 測試「社團」相關字眼
        self.assertEqual(_detect_priority_source("社團經費補助"), "6228687cc02e7827840235.pdf")
        
        # 測試無匹配關鍵字時，應回傳空字串
        self.assertEqual(_detect_priority_source("東吳大學的校長是誰"), "")
        self.assertEqual(_detect_priority_source(""), "")

    def test_rrf_fusion(self):
        """測試 RRF (倒數排序融合) 演算法在多個密集/稀疏檢索結果下的融合與去重邏輯"""
        # 建立模擬的檢索結果 Document
        doc1 = Document(page_content="請假必須於一週內辦理", metadata={"source": "law1.pdf"})
        doc2 = Document(page_content="工讀金由學務處核發", metadata={"source": "law2.pdf"})
        doc3 = Document(page_content="宿舍內禁止吸菸", metadata={"source": "law3.pdf"})
        
        # 模擬 Dense (密集向量) 檢索結果列表（包含多組 Query 的搜尋結果）
        dense_results = [
            [doc1, doc2],  # 第一組查詢結果
            [doc2, doc3]   # 第二組查詢結果
        ]
        
        # 模擬 Sparse (BM25 稀疏字詞) 檢索結果列表
        sparse_results = [
            [doc3, doc1],
            [doc1]
        ]
        
        # 進行 RRF 排序融合 (k = 60)
        fused_results = rrf_fusion(dense_results, sparse_results, k=60)
        
        # 驗證去重：總數應為 3 個 Document
        self.assertEqual(len(fused_results), 3)
        
        # 驗證融合後的 Document 內容是否正確
        contents = [d.page_content for d in fused_results]
        self.assertIn("請假必須於一週內辦理", contents)
        self.assertIn("工讀金由學務處核發", contents)
        self.assertIn("宿舍內禁止吸菸", contents)
        
    def test_system_status_structure(self):
        """測試後端健康狀態 API 的回傳欄位結構，確保格式完全正確，防止前端解析出錯"""
        status = get_full_system_status()
        
        # 驗證回傳的 key 結構是否完整
        self.assertIn("db_status", status)
        self.assertIn("pdf_count", status)
        self.assertIn("faq_count", status)
        self.assertIn("ollama_status", status)
        self.assertIn("loaded_files", status)
        
        # 驗證型別與基本值限制
        self.assertIn(status["db_status"], ["ready", "outdated", "empty"])
        self.assertIsInstance(status["pdf_count"], int)
        self.assertIsInstance(status["faq_count"], int)
        self.assertIn(status["ollama_status"], ["online", "offline"])
        self.assertIsInstance(status["loaded_files"], list)

if __name__ == "__main__":
    unittest.main()
