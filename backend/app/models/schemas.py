from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class DocumentStatus(str, Enum):
    pending    = "pending"
    extracting = "extracting"
    chunking   = "chunking"
    embedding  = "embedding"
    indexed    = "indexed"
    failed     = "failed"

class SearchMode(str, Enum):
    keyword  = "keyword"
    semantic = "semantic"

class LLMProvider(str, Enum):
    openrouter = "openrouter"
    openai     = "openai"
    anthropic  = "anthropic"
    ollama     = "ollama"


# ── Document Schemas ───────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    file_id:    UUID
    filename:   str
    status:     DocumentStatus
    created_at: datetime

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id:            UUID
    filename:           str
    file_type:          str
    minio_path:         str
    status:             str
    error_message:      Optional[str]
    size_bytes:         Optional[int]
    created_at:         datetime
    updated_at:         datetime
    parent_chunk_count: Optional[int] = None
    child_chunk_count:  Optional[int] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total:     int
    page:      int
    limit:     int

class DocumentStatusResponse(BaseModel):
    file_id:       UUID
    status:        str
    error_message: Optional[str]
    updated_at:    datetime


# ── Chunk Schemas ──────────────────────────────────────────────────────────────

class ParentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    parent_chunk_id:  UUID
    chunk_number:     int
    page_number:      int
    chunk_type:       str
    chunk_text:       str
    child_chunk_count: Optional[int] = None
    metadata:         dict = {}

class ChunkListResponse(BaseModel):
    chunks: List[ParentChunkResponse]
    total:  int
    page:   int
    limit:  int


# ── Query Schemas ──────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query:   str         = Field(..., min_length=1, max_length=2000)
    mode:    SearchMode  = SearchMode.semantic
    file_id: Optional[UUID] = None

class SourceReference(BaseModel):
    parent_chunk_id: UUID
    file_id:         UUID
    filename:        str
    page_number:     int
    chunk_text:      str
    score:           Optional[float] = None

class QueryResponse(BaseModel):
    query_id:   UUID
    answer:     str
    mode:       str
    file_id:    Optional[UUID]
    sources:    List[SourceReference]
    cached:     bool
    created_at: datetime


# ── History Schemas ────────────────────────────────────────────────────────────

class HistoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query_id:      UUID
    query_text:    str
    answer_text:   Optional[str]
    search_mode:   str
    file_id:       Optional[UUID]
    sources:       List[Any]
    cached:        bool
    status:        str
    error_message: Optional[str]
    created_at:    datetime

class HistoryListResponse(BaseModel):
    history: List[HistoryItemResponse]
    total:   int
    page:    int
    limit:   int


# ── Health Schemas ─────────────────────────────────────────────────────────────

class ServiceStatus(BaseModel):
    api:           str
    celery:        str
    minio:         str
    postgresql:    str
    elasticsearch: str
    redis:         str

class HealthResponse(BaseModel):
    status:     str
    services:   ServiceStatus
    checked_at: datetime

class StatsResponse(BaseModel):
    total_documents:   int
    indexed_documents: int
    failed_documents:  int
    queries_today:     int
    total_queries:     int
    recent_documents:  List[DocumentResponse]
    recent_queries:    List[HistoryItemResponse]


# ── Settings Schemas ───────────────────────────────────────────────────────────

class LLMSettings(BaseModel):
    provider:  str
    model:     str
    api_key:   Optional[str] = None
    base_url:  Optional[str] = None

class SearchSettings(BaseModel):
    default_mode:  str
    top_k:         int
    reranker_top_n: int

class CacheSettings(BaseModel):
    enabled:     bool
    ttl_seconds: int

class AppSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    llm:       LLMSettings
    search:    SearchSettings
    cache:     CacheSettings
    embedding_model: str

class AppSettingsUpdateRequest(BaseModel):
    llm:       Optional[LLMSettings]    = None
    search:    Optional[SearchSettings] = None
    cache:     Optional[CacheSettings]  = None
    embedding_model: Optional[str]      = None


# ── Generic ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
