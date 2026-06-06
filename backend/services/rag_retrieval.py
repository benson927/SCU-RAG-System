import heapq
import json
import os
from typing import Optional

import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi


_bm25_cache = {
    "db_id": None,
    "pdf_texts": [],
    "pdf_metadatas": [],
    "bm25_pdf": None,
}
_filter_support_cache = {}


def reset_retrieval_caches() -> None:
    global _bm25_cache, _filter_support_cache
    _bm25_cache = {
        "db_id": None,
        "pdf_texts": [],
        "pdf_metadatas": [],
        "bm25_pdf": None,
    }
    _filter_support_cache = {}


def dedupe_queries(queries: list, limit: int = 4) -> list:
    deduped = []
    seen = set()
    for query in queries:
        cleaned = query.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            deduped.append(cleaned)
        if len(deduped) >= limit:
            break
    return deduped


def rrf_fusion(dense_results_list: list, sparse_results_list: list, k: int = 60) -> list:
    rrf_scores = {}
    doc_map = {}

    def add_ranks(results_list):
        for results in results_list:
            for rank, doc in enumerate(results):
                doc_id = doc.page_content
                doc_map[doc_id] = doc
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    add_ranks(dense_results_list)
    add_ranks(sparse_results_list)
    sorted_docs = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
    return [doc_map[doc_id] for doc_id, _score in sorted_docs]


def get_pdf_bm25_index(db) -> dict:
    global _bm25_cache
    if _bm25_cache["db_id"] == id(db):
        return _bm25_cache

    all_data = db.get()
    pdf_texts = []
    pdf_metadatas = []
    for text, metadata in zip(
        all_data.get("documents", []),
        all_data.get("metadatas", []),
    ):
        if not metadata.get("faq_question"):
            pdf_texts.append(text)
            pdf_metadatas.append(metadata)

    bm25_pdf = None
    if pdf_texts:
        bm25_pdf = BM25Okapi([list(jieba.cut(text)) for text in pdf_texts])

    _bm25_cache = {
        "db_id": id(db),
        "pdf_texts": pdf_texts,
        "pdf_metadatas": pdf_metadatas,
        "bm25_pdf": bm25_pdf,
    }
    return _bm25_cache


def filter_cache_key(filter_metadata: dict) -> str:
    return json.dumps(filter_metadata, sort_keys=True, ensure_ascii=False)


def split_dense_docs_by_type(docs: list) -> tuple:
    faq_docs = [doc for doc in docs if doc.metadata.get("is_faq") is True]
    pdf_docs = [doc for doc in docs if doc.metadata.get("is_faq") is not True]
    return faq_docs, pdf_docs


def similarity_search_with_optional_filter(
    db,
    query: str,
    k: int,
    filter_metadata: dict,
    fallback_on_empty: bool = True,
) -> tuple:
    cache_key = filter_cache_key(filter_metadata)
    if _filter_support_cache.get(cache_key) is False:
        return [], False

    try:
        docs = db.similarity_search(query, k=k, filter=filter_metadata)
        if fallback_on_empty and not docs:
            return [], False
        _filter_support_cache[cache_key] = True
        return docs, True
    except Exception as exc:
        print(f"⚠️ Chroma metadata filter 不可用，改用 Python 層分類 fallback: {exc}")
        _filter_support_cache[cache_key] = False
        return [], False


def retrieve_dense_candidates(db, query: str) -> tuple:
    faq_docs, faq_filter_ok = similarity_search_with_optional_filter(
        db,
        query,
        k=4,
        filter_metadata={"is_faq": True},
    )
    pdf_docs, pdf_filter_ok = similarity_search_with_optional_filter(
        db,
        query,
        k=8,
        filter_metadata={"is_faq": {"$ne": True}},
    )
    if faq_filter_ok and pdf_filter_ok:
        return faq_docs[:4], pdf_docs[:8]

    fallback_docs = db.similarity_search(query, k=30)
    fallback_faq_docs, fallback_pdf_docs = split_dense_docs_by_type(fallback_docs)
    if not faq_filter_ok:
        faq_docs = fallback_faq_docs[:4]
    if not pdf_filter_ok:
        pdf_docs = fallback_pdf_docs[:8]
    return faq_docs[:4], pdf_docs[:8]


def bm25_top_pdf_docs(
    bm25_pdf,
    pdf_texts: list,
    pdf_metadatas: list,
    tokenized_query: list,
    n: int = 4,
) -> list:
    scores = bm25_pdf.get_scores(tokenized_query)
    top_n = min(n, len(pdf_texts))
    top_indices = heapq.nlargest(
        top_n,
        range(len(pdf_texts)),
        key=lambda index: scores[index],
    )
    return [
        Document(page_content=pdf_texts[index], metadata=pdf_metadatas[index])
        for index in top_indices
        if scores[index] > 0
    ]


def doc_identity(doc: Document) -> tuple:
    metadata = doc.metadata or {}
    source = os.path.basename(metadata.get("source", ""))
    page = metadata.get("page", "")
    content = metadata.get("original_content") or doc.page_content or ""
    return source, page, " ".join(content.split())[:220]


def doc_matches_source(doc: Document, source_alias: str) -> bool:
    metadata = doc.metadata or {}
    return (
        source_alias == metadata.get("source_alias")
        or source_alias in metadata.get("source", "")
    )


def dedupe_documents_by_identity(
    docs: list,
    limit: Optional[int] = None,
) -> list:
    deduped = []
    seen = set()
    for doc in docs:
        key = doc_identity(doc)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(doc)
        if limit is not None and len(deduped) >= limit:
            break
    return deduped


def priority_source_pdf_docs(
    bm25_index: dict,
    query: str,
    priority_src: str,
    n: int = 4,
) -> list:
    if not priority_src:
        return []

    candidate_pairs = [
        (text, metadata)
        for text, metadata in zip(
            bm25_index.get("pdf_texts", []),
            bm25_index.get("pdf_metadatas", []),
        )
        if priority_src == metadata.get("source_alias")
        or priority_src in metadata.get("source", "")
    ]
    if not candidate_pairs:
        return []

    candidate_texts = [text for text, _metadata in candidate_pairs]
    candidate_metadatas = [metadata for _text, metadata in candidate_pairs]
    tokenized_query = list(jieba.cut(query))
    if tokenized_query:
        bm25 = BM25Okapi([list(jieba.cut(text)) for text in candidate_texts])
        docs = bm25_top_pdf_docs(
            bm25,
            candidate_texts,
            candidate_metadatas,
            tokenized_query,
            n=n,
        )
        if docs:
            return docs

    ordered_pairs = sorted(
        candidate_pairs,
        key=lambda pair: pair[1].get("page", 0),
    )
    return [
        Document(page_content=text, metadata=metadata)
        for text, metadata in ordered_pairs[:n]
    ]
