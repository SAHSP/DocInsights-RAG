from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "rag_pipeline",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,             # ack only after task completes (safer)
    worker_prefetch_multiplier=1,    # one task at a time per worker (memory intensive: ML models)
    task_routes={
        "app.workers.tasks.process_document": {"queue": "ingestion"},
    },
)
