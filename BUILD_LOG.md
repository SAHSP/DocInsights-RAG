# RAG Pipeline — Build Log

> **Purpose:** Live build tracker. Updated at every step so work can be resumed from any point.
> **Python:** 3.11.1 | **Started:** 2026-04-01

---

## Environment Setup

| Component | Status | Location / Port |
|---|---|---|
| Python | ✅ 3.11.1 | local |
| PostgreSQL | ✅ 16.13 | localhost:5432 |
| Elasticsearch | ✅ local | localhost:9200 |
| MinIO | ✅ local | localhost:9000 |
| Redis | ✅ Docker | localhost:6379 |
| venv | ⬜ pending | `backend/.venv` |

---

## File Creation Progress

### Phase 0 — Project Setup
- [x] `BUILD_LOG.md` — this file
- [x] `.gitignore`
- [x] `backend/requirements.txt`
- [x] `backend/.env.example`
- [x] `backend/setup.md`
- [x] `backend/migrations/schema.sql`

### Phase 1 — Core Infrastructure
- [x] `backend/app/__init__.py`
- [x] `backend/app/core/__init__.py`
- [x] `backend/app/core/config.py`
- [x] `backend/app/core/database.py`
- [x] `backend/app/core/elasticsearch.py`
- [x] `backend/app/core/minio_client.py`
- [x] `backend/app/core/redis_client.py`

### Phase 2 — Models
- [x] `backend/app/models/__init__.py`
- [x] `backend/app/models/database.py`
- [x] `backend/app/models/schemas.py`

### Phase 3 — Services
- [x] `backend/app/services/__init__.py`
- [x] `backend/app/services/extraction.py`
- [x] `backend/app/services/chunking.py`
- [x] `backend/app/services/embedding.py`
- [x] `backend/app/services/storage.py`
- [x] `backend/app/services/search.py`
- [x] `backend/app/services/reranker.py`
- [x] `backend/app/services/llm.py`

### Phase 4 — Celery Workers
- [x] `backend/app/workers/__init__.py`
- [x] `backend/app/workers/celery_app.py`
- [x] `backend/app/workers/tasks.py`

### Phase 5 — API Routes
- [x] `backend/app/api/__init__.py`
- [x] `backend/app/api/routes/__init__.py`
- [x] `backend/app/api/routes/documents.py`
- [x] `backend/app/api/routes/query.py`
- [x] `backend/app/api/routes/history.py`
- [x] `backend/app/api/routes/health.py`
- [x] `backend/app/api/routes/settings_routes.py`

### Phase 6 — Entry Point
- [x] `backend/app/main.py`

### Next Steps
- [ ] Create `.env` from `.env.example` (user action)
- [ ] Create `rag_db` PostgreSQL database + run `schema.sql` (user action)
- [ ] Create venv + install requirements (user action)
- [ ] Run `uvicorn app.main:app --reload` — verify startup
- [ ] Run Celery worker
- [ ] Upload first test document
- [ ] Run first test query

---

## Decision Log

| # | Decision | Value |
|---|---|---|
| 1 | Chunking strategy | Hierarchical Parent-Child only |
| 2 | Parent chunk size | ~900 tokens |
| 3 | Child chunk size | target 400 tokens, max 500 |
| 4 | Child overlap | 20 tokens |
| 5 | Search modes | Keyword (BM25) or Semantic (kNN) |
| 6 | Retrieval | Top-20 child chunks → resolve parents → rerank top-5 |
| 7 | Embedding model | BAAI/bge-large-en-v1.5 (1024-dim) |
| 8 | Reranker | BAAI/bge-reranker-base |
| 9 | LLM default | OpenRouter (pluggable) |
| 10 | OCR | Phase 2 (not in this build) |
| 11 | Tokenizer role | Ruler inside chunker — not a separate stage |

---

## Last Updated
- Step: BUILD_LOG.md created
- Next: .gitignore, requirements.txt, .env.example, schema.sql
