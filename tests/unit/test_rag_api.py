import os
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import router as rag_router_module
from backend.security import reset_rate_limits


class TestRagApi(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "MAX_QUERY_LENGTH": "20",
                "RAG_TIMEOUT_SECONDS": "1",
                "RAG_MAX_CONCURRENCY": "1",
                "RAG_RATE_LIMIT": "100",
            },
            clear=False,
        )
        self.environment.start()
        reset_rate_limits()
        app = FastAPI()
        app.include_router(rag_router_module.router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        reset_rate_limits()
        self.environment.stop()

    def test_rejects_empty_and_oversized_queries(self):
        self.assertEqual(
            self.client.post("/api/rag", json={"query": ""}).status_code,
            422,
        )
        whitespace = self.client.post("/api/rag", json={"query": "   "})
        self.assertEqual(whitespace.status_code, 422)
        self.assertEqual(whitespace.json()["detail"], "問題內容不可為空。")
        response = self.client.post("/api/rag", json={"query": "x" * 21})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "問題內容過長。")

    def test_internal_error_is_not_exposed(self):
        with (
            patch.object(
                rag_router_module,
                "query_rag",
                side_effect=RuntimeError("private provider detail"),
            ),
            patch.object(rag_router_module.logger, "exception"),
        ):
            response = self.client.post("/api/rag", json={"query": "請假規則"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private provider detail", response.text)

    def test_timeout_returns_gateway_timeout(self):
        def slow_query(*_args, **_kwargs):
            time.sleep(0.05)
            return {"answer": "late", "sources": []}

        with (
            patch.dict(os.environ, {"RAG_TIMEOUT_SECONDS": "0.01"}, clear=False),
            patch.object(rag_router_module, "query_rag", side_effect=slow_query),
            patch.object(rag_router_module.logger, "warning"),
        ):
            response = self.client.post("/api/rag", json={"query": "請假規則"})
        self.assertEqual(response.status_code, 504)
        time.sleep(0.06)

    def test_rate_limit(self):
        reset_rate_limits()
        with patch.dict(os.environ, {"RAG_RATE_LIMIT": "1"}, clear=False), patch.object(
            rag_router_module,
            "query_rag",
            return_value={"answer": "ok", "sources": []},
        ):
            first = self.client.post("/api/rag", json={"query": "請假規則"})
            second = self.client.post("/api/rag", json={"query": "宿舍規則"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)


if __name__ == "__main__":
    unittest.main()
