"""
Celery Task — Document Ingestion Pipeline
process_document(file_id, minio_path, filename, file_type)

Stage 1: Download from MinIO → temp file
Stage 2: Extract text/tables (pdfplumber / python-docx)
Stage 3: Hierarchical chunking (parent-child)
Stage 4: Embed child chunks (bge-large-en-v1.5)
Stage 5: Store chunks in PostgreSQL + index embeddings in Elasticsearch
Stage 6: Update document status to 'indexed'
"""
import logging
import os
import tempfile
import traceback

from app.workers.celery_app import celery_app
from app.core.database import get_db_session
from app.core import minio_client as minio
from app.services.extraction import extract_document
from app.services.chunking import chunk_document
from app.services.embedding import embed_chunks
from app.services.storage import (
    update_document_status,
    store_chunks,
    index_embeddings,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.process_document",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_document(
    self,
    file_id: str,
    minio_path: str,
    filename: str,
    file_type: str,
) -> dict:
    """
    Full ingestion pipeline for one document.
    Updates document.status at each stage for frontend progress tracking.
    """
    db = get_db_session()
    tmp_path = None

    try:
        # ── Stage 1: Download from MinIO ──────────────────────────────────────
        logger.info(f"[{file_id}] Stage 1: Downloading from MinIO: {minio_path}")
        update_document_status(db, file_id, "extracting")

        suffix = f".{file_type}"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(tmp_fd)

        minio.download_file(minio_path, tmp_path)
        logger.info(f"[{file_id}] Downloaded to: {tmp_path}")

        # ── Stage 2: Extraction ────────────────────────────────────────────────
        logger.info(f"[{file_id}] Stage 2: Extracting content...")
        extracted = extract_document(tmp_path, file_id, filename, file_type)

        if not extracted.pages:
            raise ValueError("Extraction produced no usable pages. Document may be empty or fully scanned.")

        logger.info(f"[{file_id}] Extracted {len(extracted.pages)} page(s).")

        # ── Stage 3: Chunking ──────────────────────────────────────────────────
        logger.info(f"[{file_id}] Stage 3: Chunking...")
        update_document_status(db, file_id, "chunking")

        parent_chunks = chunk_document(extracted)
        if not parent_chunks:
            raise ValueError("Chunking produced no chunks.")

        total_children = sum(len(p.children) for p in parent_chunks)
        logger.info(f"[{file_id}] {len(parent_chunks)} parents, {total_children} children.")

        # ── Stage 4: Embedding ─────────────────────────────────────────────────
        logger.info(f"[{file_id}] Stage 4: Embedding {total_children} child chunks...")
        update_document_status(db, file_id, "embedding")

        # Flatten all child texts in document order
        all_child_texts = [
            child.chunk_text
            for parent in parent_chunks
            for child in parent.children
        ]
        embeddings = embed_chunks(all_child_texts)

        logger.info(f"[{file_id}] Generated {len(embeddings)} embeddings.")

        # ── Stage 5: Store in PostgreSQL + Elasticsearch ───────────────────────
        logger.info(f"[{file_id}] Stage 5: Storing chunks and indexing embeddings...")
        store_chunks(db, parent_chunks)
        index_embeddings(parent_chunks, embeddings)

        # ── Stage 6: Finalize ──────────────────────────────────────────────────
        update_document_status(db, file_id, "indexed")
        logger.info(f"[{file_id}] ✅ Pipeline complete.")

        return {
            "file_id":       file_id,
            "status":        "indexed",
            "parent_chunks": len(parent_chunks),
            "child_chunks":  total_children,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"[{file_id}] ❌ Pipeline failed: {error_msg}")
        logger.debug(traceback.format_exc())
        update_document_status(db, file_id, "failed", error_message=error_msg)
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc

    finally:
        db.close()
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.debug(f"[{file_id}] Temp file cleaned up: {tmp_path}")
