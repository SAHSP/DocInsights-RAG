"""
FastAPI application entry point.
Startup: verify all service connections, create ES index, create MinIO bucket.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.elasticsearch import ensure_index_exists
from app.core.minio_client import ensure_bucket_exists
from app.core.redis_client import ping_redis
from app.api.routes import documents, query, history, health, settings_routes

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup checks before accepting requests."""
    logger.info("=" * 60)
    logger.info(f"  {settings.app_name} — Starting up")
    logger.info("=" * 60)

    # Elasticsearch — check connectivity and create index
    try:
        ensure_index_exists()
        logger.info("✅ Elasticsearch: connected, index ready.")
    except Exception as e:
        logger.error(f"❌ Elasticsearch: {e}")

    # MinIO — check connectivity and create bucket
    try:
        ensure_bucket_exists()
        logger.info("✅ MinIO: connected, bucket ready.")
    except Exception as e:
        logger.error(f"❌ MinIO: {e}")

    # Redis
    if ping_redis():
        logger.info("✅ Redis: connected.")
    else:
        logger.error("❌ Redis: unreachable.")

    logger.info("Startup complete — API ready.")
    yield
    logger.info("Shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    description="Self-hosted RAG pipeline: document ingestion, semantic/keyword search, reranking, LLM answer generation.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS (allow React dev server) ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(documents.router,       prefix=API_PREFIX)
app.include_router(query.router,           prefix=API_PREFIX)
app.include_router(history.router,         prefix=API_PREFIX)
app.include_router(health.router,          prefix=API_PREFIX)
app.include_router(settings_routes.router, prefix=API_PREFIX)


@app.get("/", tags=["Root"])
def root():
    return {"message": f"{settings.app_name} API is running.", "docs": "/docs"}
