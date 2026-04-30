"""
/query — Submit a query; returns answer + sources
Full pipeline: cache check → embed → search → resolve → rerank → LLM → cache
"""
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_cached_query, set_cached_query
from app.core.config import settings
from app.models.database import QueryHistory, AppSettings
from app.models.schemas import QueryRequest, QueryResponse, SourceReference
from app.services.embedding import embed_query
from app.services.search import search_keyword, search_semantic
from app.services.storage import resolve_parents_from_children
from app.services.reranker import rerank
from app.services.llm import generate_answer

router = APIRouter(prefix="/query", tags=["Query"])
logger = logging.getLogger(__name__)


@router.post("", response_model=QueryResponse)
def run_query(
    request: QueryRequest,
    db: Session = Depends(get_db),
):
    """
    Full RAG query pipeline:
    1. Redis cache check
    2. Query embedding (bge-large-en-v1.5)
    3. Elasticsearch search (keyword or semantic)
    4. Child → Parent resolution (PostgreSQL)
    5. Reranking (bge-reranker-base)
    6. LLM answer generation (OpenRouter)
    7. Cache + log result
    """
    query_text = request.query.strip()
    mode       = request.mode.value
    file_id    = str(request.file_id) if request.file_id else None

    # ── 1. Redis cache check ──────────────────────────────────────────────────
    cached_result = get_cached_query(query_text, mode, file_id)
    if cached_result:
        logger.info("Cache HIT — returning cached answer.")
        cached_result["cached"] = True
        return QueryResponse(**cached_result)

    # ── Load runtime settings (override defaults if DB settings exist) ────────
    db_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    run_model   = db_settings.llm_model    if db_settings else settings.openrouter_model
    run_api_key = db_settings.llm_api_key  if db_settings else settings.openrouter_api_key
    run_base_url = db_settings.llm_base_url if db_settings else settings.openrouter_base_url
    cache_enabled = db_settings.cache_enabled if db_settings else True
    cache_ttl     = db_settings.cache_ttl     if db_settings else settings.cache_ttl_seconds
    top_k         = db_settings.top_k         if db_settings else settings.search_top_k_children
    top_n         = db_settings.reranker_top_n if db_settings else settings.reranker_top_n

    try:
        # ── 2. Embed query ────────────────────────────────────────────────────
        query_vector = embed_query(query_text)

        # ── 3. Elasticsearch search ───────────────────────────────────────────
        if mode == "keyword":
            hits = search_keyword(query_text, file_id=file_id, top_k=top_k)
        else:
            hits = search_semantic(query_vector, file_id=file_id, top_k=top_k)

        if not hits:
            answer = "No relevant content was found in the documents for your query."
            sources = []
        else:
            # ── 4. Child → Parent resolution ─────────────────────────────────
            child_ids = [h["child_chunk_id"] for h in hits]
            parent_candidates = resolve_parents_from_children(db, child_ids)

            # ── 5. Rerank parent chunks ───────────────────────────────────────
            reranked = rerank(query_text, parent_candidates, top_n=top_n)

            # ── 6. LLM answer generation ──────────────────────────────────────
            answer = generate_answer(
                query=query_text,
                parent_chunks=reranked,
                model=run_model,
                api_key=run_api_key,
                base_url=run_base_url,
            )

            sources = [
                SourceReference(
                    parent_chunk_id=uuid.UUID(c["parent_chunk_id"]),
                    file_id=uuid.UUID(c["file_id"]),
                    filename=c["filename"],
                    page_number=c["page_number"],
                    chunk_text=c["chunk_text"][:300] + "..." if len(c["chunk_text"]) > 300 else c["chunk_text"],
                    score=c.get("reranker_score"),
                )
                for c in reranked
            ]

        # ── 7. Log to query_history ───────────────────────────────────────────
        history = QueryHistory(
            query_text=query_text,
            answer_text=answer,
            search_mode=mode,
            file_id=uuid.UUID(file_id) if file_id else None,
            sources=[s.model_dump(mode="json") for s in sources],
            cached=False,
            status="answered",
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        response_data = QueryResponse(
            query_id=history.query_id,
            answer=answer,
            mode=mode,
            file_id=uuid.UUID(file_id) if file_id else None,
            sources=sources,
            cached=False,
            created_at=history.created_at,
        )

        # ── Cache result ──────────────────────────────────────────────────────
        if cache_enabled:
            set_cached_query(query_text, mode, file_id, response_data.model_dump(mode="json"), ttl=cache_ttl)

        return response_data

    except Exception as exc:
        logger.error(f"Query pipeline failed: {exc}")
        # Log failed query
        history = QueryHistory(
            query_text=query_text,
            search_mode=mode,
            file_id=uuid.UUID(file_id) if file_id else None,
            cached=False,
            status="failed",
            error_message=str(exc),
        )
        db.add(history)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")
