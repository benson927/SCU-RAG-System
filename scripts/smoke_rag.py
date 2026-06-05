import argparse
from pathlib import Path
import sys

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.services.rag_service import ensure_ollama_running, query_rag


CASES = [
    ("學生工讀時薪是多少？", ("工讀",)),
    ("心理調適假可以請幾天？", ("Leave", "請假")),
    ("校外宿舍可以隨意進入寢室檢查嗎？", ("宿舍", "檢查")),
    (
        "期末考缺考想請假，最晚幾天內提出？要送去哪個單位審核？",
        ("Leave", "請假", "教務"),
    ),
]


def run_smoke(limit: int | None = None) -> None:
    ensure_ollama_running()
    base_url = get_settings().ollama_base_url
    try:
        response = requests.get(base_url, timeout=3)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Ollama is not available at {base_url}") from exc

    cases = CASES[:limit] if limit else CASES
    for question, expected_terms in cases:
        result = query_rag(question)
        if not result.get("answer"):
            raise AssertionError(f"Empty answer for: {question}")
        searchable = " ".join(
            [
                result["answer"],
                *result.get("sources", []),
                *(source.get("content", "") for source in result.get("detailed_sources", [])),
            ]
        )
        if not any(term in searchable for term in expected_terms):
            raise AssertionError(f"Expected relevant source for: {question}")
        print(f"OK: {question}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run live Ollama RAG smoke checks.")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run_smoke(args.limit)
