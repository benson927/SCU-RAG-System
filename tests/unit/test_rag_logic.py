import unittest
import sys
import os
import json
import tempfile
from unittest.mock import patch

# 確保後端目錄在 Python Path 中以利載入 backend 模組
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.append(_CURRENT_DIR)

from backend.services import rag_service
from backend.services.rag_service import (
    _bm25_top_pdf_docs,
    _build_clarification_message,
    _build_system_prompt,
    _dedupe_documents_by_identity,
    _dedupe_queries,
    _detect_priority_source,
    _is_under_specified_query,
    _iter_active_faq_entries,
    _priority_source_pdf_docs,
    _retrieve_dense_candidates,
    _similarity_search_with_optional_filter,
    get_full_system_status,
    rrf_fusion,
)
from langchain_core.documents import Document

class FakeVectorDb:
    def __init__(self, filter_supported=True):
        self.filter_supported = filter_supported
        self.calls = []
        self.faq_docs = [
            Document(page_content=f"faq {i}", metadata={"is_faq": True, "source": "faq.pdf"})
            for i in range(6)
        ]
        self.pdf_docs = [
            Document(page_content=f"pdf {i}", metadata={"source": "law.pdf"})
            for i in range(10)
        ]

    def similarity_search(self, query, k=4, filter=None):
        self.calls.append({"query": query, "k": k, "filter": filter})
        if filter is not None and not self.filter_supported:
            raise ValueError("filter not supported")
        if filter == {"is_faq": True}:
            return self.faq_docs[:k]
        if filter == {"is_faq": {"$ne": True}}:
            return self.pdf_docs[:k]
        return (self.faq_docs + self.pdf_docs)[:k]

class FakeBM25:
    def __init__(self, scores):
        self.scores = scores
        self.score_calls = 0

    def get_scores(self, tokenized_query):
        self.score_calls += 1
        return self.scores

class EmptyThenHitVectorDb:
    def __init__(self):
        self.calls = []

    def similarity_search(self, query, k=4, filter=None):
        self.calls.append({"query": query, "k": k, "filter": filter})
        if len(self.calls) == 1:
            return []
        return [Document(page_content="hit", metadata={"is_faq": True})]

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

    def test_under_specified_query_detection(self):
        """過短關鍵字應先請使用者補充，避免模型對模糊問題硬答並產生幻覺"""
        self.assertTrue(_is_under_specified_query("碩士"))
        self.assertTrue(_is_under_specified_query("研究生"))
        self.assertTrue(_is_under_specified_query(""))

        self.assertFalse(_is_under_specified_query("碩士班優秀新生獎勵的申請資格是什麼？"))
        self.assertFalse(_is_under_specified_query("研究生獎助學金怎麼分配？"))
        self.assertFalse(_is_under_specified_query("工讀時薪是多少"))

    def test_clarification_examples_follow_query_keyword(self):
        """模糊查詢的追問範例應依關鍵字變化，不應固定顯示碩士獎學金例句"""
        bachelor_message = _build_clarification_message("學士")
        self.assertIn("學士班學生可以申請哪些獎助學金？", bachelor_message)
        self.assertNotIn("碩士班優秀新生獎勵的申請資格是什麼？", bachelor_message)

        dorm_message = _build_clarification_message("宿舍")
        self.assertIn("校外宿舍可以隨意進入寢室檢查嗎？", dorm_message)

        generic_message = _build_clarification_message("法規")
        self.assertIn("法規相關規章的申請資格是什麼？", generic_message)

    def test_prompt_does_not_leak_leave_rules_into_scholarship_questions(self):
        """非請假問題不應帶入請假規則或錯誤來源範例，避免污染回答來源"""
        prompt = _build_system_prompt(
            "碩士班優秀新生獎勵的申請資格是什麼？",
            ["東吳大學碩、博士班優秀新生獎勵辦法 (第 1 頁)"],
        )

        self.assertIn("東吳大學碩、博士班優秀新生獎勵辦法 (第 1 頁)", prompt)
        self.assertIn("回答內文不要自行新增", prompt)
        self.assertNotIn("學生請假規則", prompt)
        self.assertNotIn("一般請假", prompt)
        self.assertNotIn("五個工作日", prompt)
        self.assertIn("至少標註 2 到 5 個重點", prompt)
        self.assertIn("不得隨意進入", prompt)

    def test_prompt_keeps_leave_rules_for_leave_questions(self):
        """請假問題仍保留請假專用防混淆提示"""
        prompt = _build_system_prompt(
            "期末考請假期限是多久？",
            ["學生請假規則 (第 3 頁)"],
        )

        self.assertIn("一般請假", prompt)
        self.assertIn("五個工作日", prompt)

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

    def test_dedupe_queries_preserves_order_and_limit(self):
        """查詢擴展結果應保留順序去重，避免重複檢索"""
        queries = ["工讀", " 工讀 ", "WORK", "work", "宿舍", "請假"]

        deduped = _dedupe_queries(queries, limit=3)

        self.assertEqual(deduped, ["工讀", "WORK", "宿舍"])

    def test_bm25_top_pdf_docs_scores_once(self):
        """BM25 top docs 應只呼叫一次 get_scores，避免 get_top_n 重複計分"""
        bm25 = FakeBM25([0.0, 3.0, 0.0, 5.0, 1.0])
        pdf_texts = ["doc0", "doc1", "doc2", "doc3", "doc4"]
        pdf_metadatas = [{"source": f"law{i}.pdf"} for i in range(len(pdf_texts))]

        docs = _bm25_top_pdf_docs(bm25, pdf_texts, pdf_metadatas, ["工讀"], n=3)

        self.assertEqual(bm25.score_calls, 1)
        self.assertEqual([d.page_content for d in docs], ["doc3", "doc1", "doc4"])

    def test_dedupe_documents_by_identity_prefers_unique_context(self):
        """同一來源頁面與內容不應重複放入 Context"""
        docs = [
            Document(page_content="同一段法規內容", metadata={"source": "law.pdf", "page": 0}),
            Document(page_content="同一段法規內容", metadata={"source": "law.pdf", "page": 0}),
            Document(page_content="另一段內容", metadata={"source": "law.pdf", "page": 1}),
        ]

        deduped = _dedupe_documents_by_identity(docs)

        self.assertEqual(len(deduped), 2)
        self.assertEqual([doc.metadata["page"] for doc in deduped], [0, 1])

    def test_priority_source_pdf_docs_falls_back_to_target_file(self):
        """主題文件未被融合排序命中時，應能從指定 PDF 補回候選 chunks"""
        bm25_index = {
            "pdf_texts": ["宿舍檢查規定", "工讀時薪規定", "宿舍退費規定"],
            "pdf_metadatas": [
                {"source": "/data/dorm.pdf", "page": 0},
                {"source": "/data/work.pdf", "page": 0},
                {"source": "/data/dorm.pdf", "page": 1},
            ],
        }

        docs = _priority_source_pdf_docs(bm25_index, "宿舍退費", "dorm.pdf", n=2)

        self.assertEqual(len(docs), 2)
        self.assertTrue(all("dorm.pdf" in doc.metadata["source"] for doc in docs))

    def test_dense_retrieval_uses_metadata_filters_when_supported(self):
        """Chroma filter 可用時，FAQ/PDF dense 檢索應分別限制 k，避免全量 k=30 搜尋"""
        rag_service._filter_support_cache = {}
        db = FakeVectorDb(filter_supported=True)

        faq_docs, pdf_docs = _retrieve_dense_candidates(db, "工讀時薪是多少")

        self.assertEqual(len(faq_docs), 4)
        self.assertEqual(len(pdf_docs), 8)
        self.assertEqual([c["k"] for c in db.calls], [4, 8])
        self.assertEqual(db.calls[0]["filter"], {"is_faq": True})
        self.assertEqual(db.calls[1]["filter"], {"is_faq": {"$ne": True}})

    def test_dense_retrieval_falls_back_when_filters_fail(self):
        """Chroma filter 不可用時，應退回 k=30 全量候選並用 Python metadata 分類"""
        rag_service._filter_support_cache = {}
        db = FakeVectorDb(filter_supported=False)

        faq_docs, pdf_docs = _retrieve_dense_candidates(db, "期末考請假期限")

        self.assertEqual(len(faq_docs), 4)
        self.assertEqual(len(pdf_docs), 8)
        self.assertEqual([c["k"] for c in db.calls], [4, 8, 30])
        self.assertIsNone(db.calls[-1]["filter"])

    def test_empty_filter_result_does_not_disable_filter_cache(self):
        """filter 空結果只應對當次 fallback，不應永久標記 filter 不可用"""
        rag_service._filter_support_cache = {}
        db = EmptyThenHitVectorDb()
        filter_metadata = {"is_faq": True}

        docs, ok = _similarity_search_with_optional_filter(db, "no hit", 4, filter_metadata)
        self.assertEqual(docs, [])
        self.assertFalse(ok)
        self.assertNotIn(rag_service._filter_cache_key(filter_metadata), rag_service._filter_support_cache)

        docs, ok = _similarity_search_with_optional_filter(db, "has hit", 4, filter_metadata)
        self.assertTrue(ok)
        self.assertEqual([d.page_content for d in docs], ["hit"])
        
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

    def test_managed_mode_filters_faqs_by_active_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = os.path.join(temp_dir, "data")
            managed_dir = os.path.join(data_dir, "managed_documents")
            os.makedirs(managed_dir)
            with open(os.path.join(data_dir, "faq_cache.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "active": {"source": "active.pdf", "page": 1, "content": "active", "faqs": ["A"]},
                        "archived": {"source": "archived.pdf", "page": 1, "content": "archived", "faqs": ["B"]},
                    },
                    handle,
                )
            manifest_path = os.path.join(managed_dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": 1,
                        "documents": [
                            {
                                "filename": "managed-active.pdf",
                                "source_alias": "active.pdf",
                            }
                        ],
                    },
                    handle,
                )

            with patch.dict(os.environ, {"DATABASE_URL": "sqlite://"}, clear=False), patch.object(
                rag_service, "DATA_DIR", data_dir
            ), patch.object(rag_service, "MANAGED_MANIFEST_PATH", manifest_path):
                entries = _iter_active_faq_entries()

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0][0]["source"], "active.pdf")
            self.assertEqual(entries[0][1], "managed-active.pdf")

if __name__ == "__main__":
    unittest.main()
