"""
/settings — Get and update runtime configuration
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import clear_all_query_cache
from app.core.config import settings as env_settings
from app.models.database import AppSettings
from app.models.schemas import (
    AppSettingsResponse, AppSettingsUpdateRequest,
    LLMSettings, SearchSettings, CacheSettings, MessageResponse,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


def _get_or_create_settings(db: Session) -> AppSettings:
    """Get the single settings row, creating it with defaults if missing."""
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not row:
        row = AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=AppSettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """Get current system configuration."""
    row = _get_or_create_settings(db)
    return AppSettingsResponse(
        llm=LLMSettings(
            provider=row.llm_provider,
            model=row.llm_model,
            api_key=None,               # never return the API key in GET
            base_url=row.llm_base_url,
        ),
        search=SearchSettings(
            default_mode=row.default_search_mode,
            top_k=row.top_k,
            reranker_top_n=row.reranker_top_n,
        ),
        cache=CacheSettings(
            enabled=row.cache_enabled,
            ttl_seconds=row.cache_ttl,
        ),
        embedding_model=row.embedding_model,
    )


@router.put("", response_model=AppSettingsResponse)
def update_settings(
    payload: AppSettingsUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update system configuration."""
    row = _get_or_create_settings(db)

    if payload.llm:
        if payload.llm.provider:  row.llm_provider = payload.llm.provider
        if payload.llm.model:     row.llm_model    = payload.llm.model
        if payload.llm.api_key:   row.llm_api_key  = payload.llm.api_key
        if payload.llm.base_url:  row.llm_base_url = payload.llm.base_url

    if payload.search:
        if payload.search.default_mode:   row.default_search_mode = payload.search.default_mode
        if payload.search.top_k:          row.top_k               = payload.search.top_k
        if payload.search.reranker_top_n: row.reranker_top_n      = payload.search.reranker_top_n

    if payload.cache:
        row.cache_enabled = payload.cache.enabled
        if payload.cache.ttl_seconds: row.cache_ttl = payload.cache.ttl_seconds

    if payload.embedding_model:
        row.embedding_model = payload.embedding_model

    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    return AppSettingsResponse(
        llm=LLMSettings(provider=row.llm_provider, model=row.llm_model, base_url=row.llm_base_url),
        search=SearchSettings(default_mode=row.default_search_mode, top_k=row.top_k, reranker_top_n=row.reranker_top_n),
        cache=CacheSettings(enabled=row.cache_enabled, ttl_seconds=row.cache_ttl),
        embedding_model=row.embedding_model,
    )


@router.post("/cache/clear", response_model=MessageResponse)
def clear_cache():
    """Flush the Redis query cache."""
    deleted = clear_all_query_cache()
    return MessageResponse(message=f"Cleared {deleted} cached query result(s).")
