import uuid
from datetime import datetime
from sqlalchemy import (
    String, Integer, Text, Boolean, BigInteger,
    ForeignKey, DateTime,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    file_id:       Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename:      Mapped[str]           = mapped_column(String(512), nullable=False)
    file_type:     Mapped[str]           = mapped_column(String(10),  nullable=False)   # pdf | docx
    minio_path:    Mapped[str]           = mapped_column(String(1024), nullable=False)
    status:        Mapped[str]           = mapped_column(String(20),  nullable=False, default="pending")
    error_message: Mapped[str | None]    = mapped_column(Text,        nullable=True)
    size_bytes:    Mapped[int | None]    = mapped_column(BigInteger,  nullable=True)
    created_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent_chunks: Mapped[list["ParentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    query_history: Mapped[list["QueryHistory"]] = relationship(
        back_populates="document",
        cascade="save-update, merge",
    )


class ParentChunk(Base):
    __tablename__ = "parent_chunks"

    parent_chunk_id: Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id:         Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("documents.file_id", ondelete="CASCADE"), nullable=False)
    page_number:     Mapped[int]        = mapped_column(Integer, nullable=False)
    chunk_number:    Mapped[int]        = mapped_column(Integer, nullable=False)     # position in document (1-based)
    chunk_text:      Mapped[str]        = mapped_column(Text,    nullable=False)
    chunk_type:      Mapped[str]        = mapped_column(String(20), nullable=False, default="text")  # text | table | mixed
    metadata_:       Mapped[dict]       = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at:      Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    document:     Mapped["Document"]         = relationship(back_populates="parent_chunks")
    child_chunks: Mapped[list["ChildChunk"]] = relationship(
        back_populates="parent_chunk",
        cascade="all, delete-orphan",
    )


class ChildChunk(Base):
    __tablename__ = "child_chunks"

    child_chunk_id:  Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_chunk_id: Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("parent_chunks.parent_chunk_id", ondelete="CASCADE"), nullable=False)
    file_id:         Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("documents.file_id", ondelete="CASCADE"), nullable=False)
    page_number:     Mapped[int]        = mapped_column(Integer, nullable=False)
    child_number:    Mapped[int]        = mapped_column(Integer, nullable=False)     # position within parent (1-based)
    chunk_text:      Mapped[str]        = mapped_column(Text,    nullable=False)
    token_count:     Mapped[int]        = mapped_column(Integer, nullable=False)
    metadata_:       Mapped[dict]       = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at:      Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    parent_chunk: Mapped["ParentChunk"] = relationship(back_populates="child_chunks")


class QueryHistory(Base):
    __tablename__ = "query_history"

    query_id:      Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_text:    Mapped[str]          = mapped_column(Text,       nullable=False)
    answer_text:   Mapped[str | None]   = mapped_column(Text,       nullable=True)
    search_mode:   Mapped[str]          = mapped_column(String(10), nullable=False)   # keyword | semantic
    file_id:       Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.file_id", ondelete="SET NULL"), nullable=True)
    sources:       Mapped[list]         = mapped_column(JSONB,      nullable=False, default=list)
    cached:        Mapped[bool]         = mapped_column(Boolean,    nullable=False, default=False)
    status:        Mapped[str]          = mapped_column(String(10), nullable=False, default="answered")  # answered | failed
    error_message: Mapped[str | None]   = mapped_column(Text,       nullable=True)
    created_at:    Mapped[datetime]     = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    document: Mapped["Document | None"] = relationship(back_populates="query_history")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id:                  Mapped[int]          = mapped_column(Integer, primary_key=True, default=1)
    llm_provider:        Mapped[str]          = mapped_column(String(50),  nullable=False, default="openrouter")
    llm_model:           Mapped[str]          = mapped_column(String(100), nullable=False, default="google/gemini-2.0-flash-exp:free")
    llm_api_key:         Mapped[str | None]   = mapped_column(Text,        nullable=True)
    llm_base_url:        Mapped[str | None]   = mapped_column(Text,        nullable=True)
    embedding_model:     Mapped[str]          = mapped_column(String(200), nullable=False, default="BAAI/bge-large-en-v1.5")
    default_search_mode: Mapped[str]          = mapped_column(String(10),  nullable=False, default="semantic")
    top_k:               Mapped[int]          = mapped_column(Integer,     nullable=False, default=20)
    reranker_top_n:      Mapped[int]          = mapped_column(Integer,     nullable=False, default=5)
    cache_enabled:       Mapped[bool]         = mapped_column(Boolean,     nullable=False, default=True)
    cache_ttl:           Mapped[int]          = mapped_column(Integer,     nullable=False, default=3600)
    updated_at:          Mapped[datetime]     = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
