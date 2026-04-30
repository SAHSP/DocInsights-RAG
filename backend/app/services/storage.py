"""
Storage Service
Responsible for writing pipeline results to PostgreSQL and Elasticsearch.
Called from the Celery worker task after each pipeline stage.
"""
import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session
from elasticsearch.helpers import bulk

from app.core.elasticsearch import es_client
from app.core.config import settings
from app.models.database import Document, ParentChunk, ChildChunk
from app.services.chunking import ParentChunkData

logger = logging.getLogger(__name__)


# ── Document Status ───────────────────────────────────────────────────────────

def update_document_status(
    db: Session,
    file_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Update the status field of a document record."""
    doc = db.query(Document).filter(Document.file_id == uuid.UUID(file_id)).first()
    if doc:
        doc.status = status
        if error_message is not None:
            doc.error_message = error_message
        db.commit()
        logger.info(f"[{file_id}] Status → {status}")


# ── Chunk Storage ─────────────────────────────────────────────────────────────

def store_chunks(
    db: Session,
    parent_chunks: list[ParentChunkData],
) -> None:
    """
    Batch insert parent and child chunks into PostgreSQL.
    Each ParentChunkData already has a pre-generated UUID (parent_chunk_id).
    Each ChildChunkData already has a pre-generated UUID (child_chunk_id).
    """
    parent_rows = []
    child_rows  = []

    for parent in parent_chunks:
        parent_rows.append(ParentChunk(
            parent_chunk_id=parent.parent_chunk_id,
            file_id=parent.file_id,
            page_number=parent.page_number,
            chunk_number=parent.chunk_number,
            chunk_text=parent.chunk_text,
            chunk_type=parent.chunk_type,
            metadata_=parent.metadata,
        ))
        for child in parent.children:
            child_rows.append(ChildChunk(
                child_chunk_id=child.child_chunk_id,
                parent_chunk_id=child.parent_chunk_id,
                file_id=child.file_id,
                page_number=child.page_number,
                child_number=child.child_number,
                chunk_text=child.chunk_text,
                token_count=child.token_count,
                metadata_=child.metadata,
            ))

    db.bulk_save_objects(parent_rows)
    db.bulk_save_objects(child_rows)
    db.commit()
    logger.info(f"Stored {len(parent_rows)} parent chunks and {len(child_rows)} child chunks in PostgreSQL.")


# ── Elasticsearch Indexing ────────────────────────────────────────────────────

def index_embeddings(
    parent_chunks: list[ParentChunkData],
    embeddings: list[list[float]],
) -> None:
    """
    Bulk index child chunks with their embeddings into Elasticsearch.
    embeddings[i] corresponds to the i-th child chunk in document order.

    Document stored per child chunk:
    {
      child_chunk_id, parent_chunk_id, file_id,
      chunk_text, embedding, page_number, chunk_type, metadata
    }
    """
    actions = []
    embed_idx = 0

    for parent in parent_chunks:
        for child in parent.children:
            if embed_idx >= len(embeddings):
                logger.error("Embeddings list is shorter than child chunk count — indexing aborted.")
                break

            actions.append({
                "_index": settings.elasticsearch_index,
                "_id":    str(child.child_chunk_id),
                "_source": {
                    "child_chunk_id":  str(child.child_chunk_id),
                    "parent_chunk_id": str(child.parent_chunk_id),
                    "file_id":         str(child.file_id),
                    "chunk_text":      child.chunk_text,
                    "embedding":       embeddings[embed_idx],
                    "page_number":     child.page_number,
                    "chunk_type":      parent.chunk_type,
                    "metadata":        {
                        **child.metadata,
                        "child_number":  child.child_number,
                        "chunk_number":  parent.chunk_number,
                    },
                },
            })
            embed_idx += 1

    success, errors = bulk(es_client, actions, raise_on_error=False)
    if errors:
        logger.error(f"Elasticsearch bulk index errors: {errors}")
    logger.info(f"Indexed {success} child chunks into Elasticsearch '{settings.elasticsearch_index}'.")


# ── Deletion ──────────────────────────────────────────────────────────────────

def delete_document_data(db: Session, file_id: str) -> None:
    """
    Delete a document and all its chunks from PostgreSQL.
    (Elasticsearch cleanup is handled separately via elasticsearch.py)
    Cascades delete to parent_chunks → child_chunks automatically.
    """
    doc = db.query(Document).filter(Document.file_id == uuid.UUID(file_id)).first()
    if doc:
        db.delete(doc)
        db.commit()
        logger.info(f"[{file_id}] Document and all chunks deleted from PostgreSQL.")


# ── Parent Chunk Fetcher (after search) ──────────────────────────────────────

def resolve_parents_from_children(
    db: Session,
    child_chunk_ids: list[str],
) -> list[dict]:
    """
    Given a list of child_chunk_ids (from Elasticsearch results),
    resolve their parent_chunk_ids and fetch the full parent chunk text.

    Returns a list of source dicts:
    { parent_chunk_id, file_id, filename, page_number, chunk_text }
    """
    if not child_chunk_ids:
        return []

    child_uuids = [uuid.UUID(cid) for cid in child_chunk_ids]

    children = (
        db.query(ChildChunk)
        .filter(ChildChunk.child_chunk_id.in_(child_uuids))
        .all()
    )

    parent_ids = list({c.parent_chunk_id for c in children})

    parents = (
        db.query(ParentChunk, Document.filename)
        .join(Document, Document.file_id == ParentChunk.file_id)
        .filter(ParentChunk.parent_chunk_id.in_(parent_ids))
        .all()
    )

    results = []
    for parent, filename in parents:
        results.append({
            "parent_chunk_id": str(parent.parent_chunk_id),
            "file_id":         str(parent.file_id),
            "filename":        filename,
            "page_number":     parent.page_number,
            "chunk_text":      parent.chunk_text,
        })

    return results
