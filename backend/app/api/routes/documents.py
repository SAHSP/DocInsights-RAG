"""
/documents — Upload, list, status, chunks, delete
"""
import os
import tempfile
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core import minio_client as minio
from app.models.database import Document, ParentChunk, ChildChunk
from app.models.schemas import (
    DocumentUploadResponse, DocumentResponse, DocumentListResponse,
    DocumentStatusResponse, ParentChunkResponse, ChunkListResponse, MessageResponse,
)
from app.workers.tasks import process_document
from app.core.elasticsearch import delete_chunks_by_file

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"pdf", "docx"}


@router.post("/upload", response_model=DocumentUploadResponse, status_code=202)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF or DOCX file. Triggers the async ingestion pipeline.
    Returns immediately with file_id and status='pending'.
    """
    # Validate file type
    original_name = file.filename or "unknown"
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{extension}'. Allowed: pdf, docx.")

    file_id    = uuid.uuid4()
    file_id_str = str(file_id)

    # Save to temp file for MinIO upload
    suffix = f".{extension}"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        # Write upload to temp file
        with os.fdopen(tmp_fd, "wb") as tmp:
            content = file.file.read()
            tmp.write(content)

        size_bytes = len(content)
        content_type = "application/pdf" if extension == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        # Upload to MinIO
        minio_path = minio.upload_file(
            file_id=file_id_str,
            filename=original_name,
            file_path=tmp_path,
            content_type=content_type,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # Register in PostgreSQL
    doc = Document(
        file_id=file_id,
        filename=original_name,
        file_type=extension,
        minio_path=minio_path,
        status="pending",
        size_bytes=size_bytes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Dispatch Celery task
    process_document.delay(
        file_id=file_id_str,
        minio_path=minio_path,
        filename=original_name,
        file_type=extension,
    )
    logger.info(f"Document uploaded: {original_name} [{file_id_str}] — pipeline queued.")

    return DocumentUploadResponse(
        file_id=doc.file_id,
        filename=doc.filename,
        status=doc.status,
        created_at=doc.created_at,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db:    Session = Depends(get_db),
):
    """List all uploaded documents with pagination."""
    offset = (page - 1) * limit
    total  = db.query(Document).count()
    docs   = db.query(Document).order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for doc in docs:
        parent_count = db.query(ParentChunk).filter(ParentChunk.file_id == doc.file_id).count()
        child_count  = db.query(ChildChunk).filter(ChildChunk.file_id  == doc.file_id).count()
        d = DocumentResponse.model_validate(doc)
        d.parent_chunk_count = parent_count
        d.child_chunk_count  = child_count
        result.append(d)

    return DocumentListResponse(documents=result, total=total, page=page, limit=limit)


@router.get("/{file_id}", response_model=DocumentResponse)
def get_document(file_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get details of a single document."""
    doc = db.query(Document).filter(Document.file_id == file_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    parent_count = db.query(ParentChunk).filter(ParentChunk.file_id == file_id).count()
    child_count  = db.query(ChildChunk).filter(ChildChunk.file_id  == file_id).count()
    d = DocumentResponse.model_validate(doc)
    d.parent_chunk_count = parent_count
    d.child_chunk_count  = child_count
    return d


@router.get("/{file_id}/status", response_model=DocumentStatusResponse)
def get_document_status(file_id: uuid.UUID, db: Session = Depends(get_db)):
    """Poll the pipeline status of a document."""
    doc = db.query(Document).filter(Document.file_id == file_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentStatusResponse(
        file_id=doc.file_id,
        status=doc.status,
        error_message=doc.error_message,
        updated_at=doc.updated_at,
    )


@router.get("/{file_id}/chunks", response_model=ChunkListResponse)
def get_document_chunks(
    file_id: uuid.UUID,
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List parent chunks for a document."""
    doc = db.query(Document).filter(Document.file_id == file_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    offset = (page - 1) * limit
    total  = db.query(ParentChunk).filter(ParentChunk.file_id == file_id).count()
    chunks = (
        db.query(ParentChunk)
        .filter(ParentChunk.file_id == file_id)
        .order_by(ParentChunk.chunk_number)
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for chunk in chunks:
        child_count = db.query(ChildChunk).filter(ChildChunk.parent_chunk_id == chunk.parent_chunk_id).count()
        c = ParentChunkResponse(
            parent_chunk_id=chunk.parent_chunk_id,
            chunk_number=chunk.chunk_number,
            page_number=chunk.page_number,
            chunk_type=chunk.chunk_type,
            chunk_text=chunk.chunk_text,
            child_chunk_count=child_count,
            metadata=chunk.metadata_ or {},
        )
        result.append(c)

    return ChunkListResponse(chunks=result, total=total, page=page, limit=limit)


@router.delete("/{file_id}", response_model=MessageResponse)
def delete_document(file_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a document, all its chunks (PostgreSQL), raw file (MinIO), and ES index entries."""
    doc = db.query(Document).filter(Document.file_id == file_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Delete from MinIO
    try:
        minio.delete_file(doc.minio_path)
    except Exception as e:
        logger.warning(f"MinIO delete failed for {doc.minio_path}: {e}")

    # Delete from Elasticsearch
    try:
        delete_chunks_by_file(str(file_id))
    except Exception as e:
        logger.warning(f"Elasticsearch delete failed for {file_id}: {e}")

    # Delete from PostgreSQL (cascades to parent+child chunks)
    db.delete(doc)
    db.commit()

    return MessageResponse(message=f"Document '{doc.filename}' deleted successfully.")
