"""
Reranker Service
Model: BAAI/bge-reranker-base (CrossEncoder)
- Takes the user query and a list of parent chunk texts
- Scores each (query, chunk_text) pair for true relevance
- Returns top-N reranked results
"""
import logging
from typing import Optional

from sentence_transformers import CrossEncoder

from app.core.config import settings

logger = logging.getLogger(__name__)

_reranker: Optional[CrossEncoder] = None


def get_reranker() -> CrossEncoder:
    """
    Lazy singleton loader.
    CrossEncoder for bge-reranker-base (~270MB).
    """
    global _reranker
    if _reranker is None:
        logger.info(f"Loading reranker model: {settings.reranker_model}")
        _reranker = CrossEncoder(settings.reranker_model)
        logger.info("Reranker model loaded.")
    return _reranker


def rerank(
    query: str,
    candidates: list[dict],
    top_n: Optional[int] = None,
) -> list[dict]:
    """
    Rerank parent chunk candidates using bge-reranker-base.

    candidates: list of dicts, each must have 'chunk_text' and 'parent_chunk_id'
                (typically the output of storage.resolve_parents_from_children)

    Returns top_n candidates, ordered by reranker score (highest first).
    Each dict has 'reranker_score' added.
    """
    top_n = top_n or settings.reranker_top_n

    if not candidates:
        return []

    reranker = get_reranker()

    # Build (query, passage) pairs for the CrossEncoder
    pairs = [(query, c["chunk_text"]) for c in candidates]

    # Score all pairs — returns a numpy array of scores
    scores = reranker.predict(pairs)

    # Attach scores and sort
    scored = [
        {**c, "reranker_score": float(score)}
        for c, score in zip(candidates, scores)
    ]
    scored.sort(key=lambda x: x["reranker_score"], reverse=True)

    return scored[:top_n]
