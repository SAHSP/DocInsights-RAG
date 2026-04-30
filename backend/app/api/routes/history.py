"""
/history — List and delete query history
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database import QueryHistory
from app.models.schemas import HistoryListResponse, HistoryItemResponse, MessageResponse

router = APIRouter(prefix="/history", tags=["History"])


@router.get("", response_model=HistoryListResponse)
def list_history(
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List all query history entries, newest first."""
    offset = (page - 1) * limit
    total  = db.query(QueryHistory).count()
    rows   = (
        db.query(QueryHistory)
        .order_by(QueryHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return HistoryListResponse(
        history=[HistoryItemResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{query_id}", response_model=HistoryItemResponse)
def get_history_item(query_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get full detail of one past query."""
    row = db.query(QueryHistory).filter(QueryHistory.query_id == query_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Query not found.")
    return HistoryItemResponse.model_validate(row)


@router.delete("/{query_id}", response_model=MessageResponse)
def delete_history_item(query_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a single query from history."""
    row = db.query(QueryHistory).filter(QueryHistory.query_id == query_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Query not found.")
    db.delete(row)
    db.commit()
    return MessageResponse(message="Query deleted from history.")
