from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional
from pathlib import Path

# Resolve .env path relative to this file
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────
    app_name: str = "RAG Pipeline"
    debug: bool = False

    # ── PostgreSQL ────────────────────────────────────────
    database_url: str

    # ── Elasticsearch ─────────────────────────────────────────────────────────
    elasticsearch_url:          str  = "https://localhost:9200"   # use https:// for ES 8.x
    elasticsearch_username:     str  = ""
    elasticsearch_password:     str  = ""
    elasticsearch_index:        str  = "rag_child_chunks"
    elasticsearch_verify_certs: bool = False   # set True in production with valid certs

    # ── MinIO ─────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_name: str = "raw-documents"
    minio_secure: bool = False

    # ── Redis / Celery ────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── LLM ───────────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemini-2.0-flash-exp:free"

    # ── Embedding & Reranker ──────────────────────────────
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"

    # ── Chunking ──────────────────────────────────────────
    child_chunk_target_tokens: int = 400
    child_chunk_max_tokens: int = 500
    child_chunk_overlap_tokens: int = 20
    parent_chunk_target_tokens: int = 900

    # ── Search ────────────────────────────────────────────
    search_top_k_children: int = 20
    reranker_top_n: int = 5

    # ── Cache ─────────────────────────────────────────────
    cache_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton — import this everywhere
settings = Settings()
