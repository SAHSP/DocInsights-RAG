"""
/health — Service health check
/stats  — Dashboard statistics
"""
from datetime import datetime, date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.elasticsearch import es_client
from app.core.minio_client import minio_client
from app.core.redis_client import ping_redis
from app.core.config import settings
from app.models.database import Document, QueryHistory
from app.models.schemas import HealthResponse, ServiceStatus, StatsResponse, DocumentResponse, HistoryItemResponse

router = APIRouter(tags=["System"])


def _check_postgresql(db: Session) -> str:
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return "online"
    except Exception:
        return "offline"


def _check_elasticsearch() -> str:
    try:
        return "online" if es_client.ping() else "offline"
    except Exception:
        return "offline"


def _check_minio() -> str:
    try:
        minio_client.list_buckets()
        return "online"
    except Exception:
        return "offline"


def _check_celery() -> str:
    try:
        from app.workers.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=1.0)
        stats = inspect.stats()
        return "online" if stats else "no workers"
    except Exception:
        return "offline"


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Check the status of all services."""
    services = ServiceStatus(
        api="online",
        celery=_check_celery(),
        minio=_check_minio(),
        postgresql=_check_postgresql(db),
        elasticsearch=_check_elasticsearch(),
        redis="online" if ping_redis() else "offline",
    )
    overall = "healthy" if all(
        v in ("online",) for v in [
            services.postgresql, services.elasticsearch,
            services.minio, services.redis
        ]
    ) else "degraded"

    return HealthResponse(status=overall, services=services, checked_at=datetime.utcnow())


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """Aggregate statistics for the dashboard."""
    today = date.today()

    total_docs   = db.query(Document).count()
    indexed_docs = db.query(Document).filter(Document.status == "indexed").count()
    failed_docs  = db.query(Document).filter(Document.status == "failed").count()

    total_queries = db.query(QueryHistory).count()
    queries_today = db.query(QueryHistory).filter(
        func.date(QueryHistory.created_at) == today
    ).count()

    recent_docs    = db.query(Document).order_by(Document.created_at.desc()).limit(5).all()
    recent_queries = db.query(QueryHistory).order_by(QueryHistory.created_at.desc()).limit(5).all()

    return StatsResponse(
        total_documents=total_docs,
        indexed_documents=indexed_docs,
        failed_documents=failed_docs,
        total_queries=total_queries,
        queries_today=queries_today,
        recent_documents=[DocumentResponse.model_validate(d) for d in recent_docs],
        recent_queries=[HistoryItemResponse.model_validate(q) for q in recent_queries],
    )
