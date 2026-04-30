"""
Search Service
Runs keyword (BM25) or semantic (kNN) search against the Elasticsearch index.
Always searches child chunks. Returns child_chunk_ids for parent resolution.
"""
import logging
from typing import Optional
from uuid import UUID

from app.core.elasticsearch import es_client
from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_keyword_query(query_text: str, file_id: Optional[str], top_k: int) -> dict:
    """BM25 match on chunk_text with optional file_id filter."""
    if file_id:
        return {
            "query": {
                "bool": {
                    "must":   {"match": {"chunk_text": {"query": query_text, "operator": "or"}}},
                    "filter": {"term": {"file_id": file_id}},
                }
            },
            "size": top_k,
        }
    return {
        "query": {"match": {"chunk_text": {"query": query_text, "operator": "or"}}},
        "size": top_k,
    }


def _build_semantic_query(query_vector: list[float], file_id: Optional[str], top_k: int) -> dict:
    """kNN ANN search on embedding field with optional file_id filter (Elasticsearch 8+ syntax)."""
    knn_block: dict = {
        "field":         "embedding",
        "query_vector":  query_vector,
        "k":             top_k,
        "num_candidates": top_k * 5,   # examine 5x candidates for better recall
    }
    if file_id:
        knn_block["filter"] = {"term": {"file_id": file_id}}

    return {"knn": knn_block}


def search_keyword(
    query_text: str,
    file_id: Optional[str] = None,
    top_k: Optional[int] = None,
) -> list[dict]:
    """
    BM25 keyword search.
    Returns: [{ child_chunk_id, score }]
    """
    top_k = top_k or settings.search_top_k_children
    body = _build_keyword_query(query_text, file_id, top_k)

    try:
        resp = es_client.search(index=settings.elasticsearch_index, body=body)
        hits = resp["hits"]["hits"]
        return [
            {"child_chunk_id": h["_id"], "score": h["_score"]}
            for h in hits
        ]
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        raise


def search_semantic(
    query_vector: list[float],
    file_id: Optional[str] = None,
    top_k: Optional[int] = None,
) -> list[dict]:
    """
    kNN semantic search.
    Returns: [{ child_chunk_id, score }]
    """
    top_k = top_k or settings.search_top_k_children
    body = _build_semantic_query(query_vector, file_id, top_k)

    try:
        resp = es_client.search(index=settings.elasticsearch_index, body=body)
        hits = resp["hits"]["hits"]
        return [
            {"child_chunk_id": h["_id"], "score": h["_score"]}
            for h in hits
        ]
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise
