# RAG Pipeline — Setup Guide

## Prerequisites
- Python 3.11.1 ✅
- PostgreSQL 16.13 (local) ✅
- Elasticsearch (local, port 9200) ✅
- MinIO (local, port 9000) ✅
- Redis (Docker, port 6379) ✅

---

## Step 1 — Create the PostgreSQL Database

Open pgAdmin or psql and run:
```sql
CREATE DATABASE rag_db;
```

Then connect to `rag_db` and run the schema:
```
psql -U postgres -d rag_db -f migrations/schema.sql
```
Or paste the contents of `migrations/schema.sql` into pgAdmin's query tool.

---

## Step 2 — Set Up Environment Variables

```
copy .env.example .env
```

Open `.env` and update:
- `DATABASE_URL` → set your PostgreSQL password
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` → match your local MinIO credentials
- `OPENROUTER_API_KEY` → get from https://openrouter.ai (free account)

Leave Elasticsearch and Redis as-is if using defaults.

---

## Step 3 — Create Virtual Environment

```
cd backend
python -m venv .venv
.venv\Scripts\activate
```

---

## Step 4 — Install Dependencies

**Install PyTorch first (CPU-only, recommended for dev on Windows):**
```
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

**Then install all other dependencies:**
```
pip install -r requirements.txt
```

> First-time model download: `bge-large-en-v1.5` (~1.3GB) and `bge-reranker-base` (~270MB)
> will be downloaded from HuggingFace automatically on first use.

---

## Step 5 — Run the API Server

From the `backend/` directory with venv activated:
```
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at:
- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/api/v1/health

---

## Step 6 — Run the Celery Worker

Open a **second terminal** in `backend/` with venv activated:
```
celery -A app.workers.celery_app worker --loglevel=info -Q ingestion
```

> The worker handles document processing asynchronously.
> The API will accept uploads without the worker, but documents will stay in 'pending' status.

---

## API Quick Reference

| Action | Method | URL |
|---|---|---|
| Upload document | `POST` | `/api/v1/documents/upload` |
| List documents | `GET` | `/api/v1/documents` |
| Check status | `GET` | `/api/v1/documents/{file_id}/status` |
| Ask a question | `POST` | `/api/v1/query` |
| View history | `GET` | `/api/v1/history` |
| Health check | `GET` | `/api/v1/health` |
| Dashboard stats | `GET` | `/api/v1/stats` |

---

## Query Example (curl)

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main findings?", "mode": "semantic"}'
```
