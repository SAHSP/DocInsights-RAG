# RAG Pipeline — Frontend ↔ Backend API Reference

> **Version:** 2.0 (matches implemented backend)
> **Last Updated:** 2026-04-01
> **Purpose:** Single source of truth for connecting the React frontend to the FastAPI backend.
> All endpoints are live and testable at `http://localhost:8000/docs`

---

## Base URL

| Environment | Base URL |
|---|---|
| Development | `http://localhost:8000/api/v1` |

All requests: `Content-Type: application/json`
File uploads: `Content-Type: multipart/form-data`

---

## Pages & What They Need

| Page | Endpoints Used |
|---|---|
| **Dashboard** | `GET /health`, `GET /stats` |
| **Documents Library** | `GET /documents`, `POST /documents/upload`, `GET /documents/{id}/status`, `DELETE /documents/{id}` |
| **Document Detail** | `GET /documents/{id}`, `GET /documents/{id}/chunks` |
| **Chat / Query** | `GET /documents` (doc selector), `POST /query` |
| **History** | `GET /history`, `DELETE /history/{id}` |
| **Settings** | `GET /settings`, `PUT /settings`, `POST /settings/cache/clear` |

---

## 1. Document Endpoints

### `POST /documents/upload`
Upload a PDF or DOCX. Immediately returns — processing happens in background.

- **Content-Type:** `multipart/form-data`
- **Body:** `file` (binary)
- **Response `202`:**
```json
{
  "file_id": "99959662-2cce-4ae6-b37c-b7f8e6897618",
  "filename": "report.pdf",
  "status": "pending",
  "created_at": "2026-04-01T08:00:00Z"
}
```
- **Error `400`:** Unsupported file type (only pdf/docx allowed)
- **Frontend action:** After upload, start polling `/documents/{file_id}/status` every 3–5s

---

### `GET /documents?page=1&limit=20`
List all documents with pagination.

- **Response `200`:**
```json
{
  "documents": [
    {
      "file_id": "uuid",
      "filename": "report.pdf",
      "file_type": "pdf",
      "status": "indexed",
      "size_bytes": 240000,
      "parent_chunk_count": 12,
      "child_chunk_count": 34,
      "created_at": "2026-04-01T08:00:00Z",
      "updated_at": "2026-04-01T08:05:00Z",
      "error_message": null
    }
  ],
  "total": 5,
  "page": 1,
  "limit": 20
}
```
- **Status values:** `pending` | `extracting` | `chunking` | `embedding` | `indexed` | `failed`

---

### `GET /documents/{file_id}`
Full detail of one document.

- **Response `200`:** Same as single item in list above (includes chunk counts)
- **Error `404`:** Document not found

---

### `GET /documents/{file_id}/status`
Lightweight status poll — call every 3–5s for in-progress documents.

- **Response `200`:**
```json
{
  "file_id": "uuid",
  "status": "embedding",
  "error_message": null,
  "updated_at": "2026-04-01T08:03:00Z"
}
```
- **Frontend action:** Stop polling when status = `indexed` or `failed`

---

### `GET /documents/{file_id}/chunks?page=1&limit=20`
List parent chunks for a document (for the chunks inspector view).

- **Response `200`:**
```json
{
  "chunks": [
    {
      "parent_chunk_id": "uuid",
      "chunk_number": 1,
      "page_number": 1,
      "chunk_type": "text",
      "chunk_text": "Full text of the parent chunk...",
      "child_chunk_count": 3,
      "metadata": { "source": "report.pdf" }
    }
  ],
  "total": 12,
  "page": 1,
  "limit": 20
}
```

---

### `DELETE /documents/{file_id}`
Delete a document, all chunks (PostgreSQL), embeddings (Elasticsearch), and raw file (MinIO).

- **Response `200`:** `{ "message": "Document 'report.pdf' deleted successfully." }`
- **Error `404`:** Document not found

---

## 2. Query Endpoint

### `POST /query`
The core RAG pipeline. Takes a question, returns an LLM answer with sources.

- **Request:**
```json
{
  "query": "What are the key responsibilities?",
  "mode": "semantic",
  "file_id": null
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | string | ✅ | 1–2000 chars |
| `mode` | string | ✅ | `"semantic"` or `"keyword"` |
| `file_id` | UUID or null | ❌ | `null` = search all documents |

- **Response `200`:**
```json
{
  "query_id": "uuid",
  "answer": "The key responsibilities include...",
  "mode": "semantic",
  "file_id": null,
  "sources": [
    {
      "parent_chunk_id": "uuid",
      "file_id": "uuid",
      "filename": "report.pdf",
      "page_number": 3,
      "chunk_text": "First 300 chars of the relevant passage...",
      "score": 0.89
    }
  ],
  "cached": false,
  "created_at": "2026-04-01T09:00:00Z"
}
```

- **Error `500`:** Pipeline error (ES down, LLM API key invalid, etc.)
- **Note:** First query after startup takes longer (model loading). Subsequent: 2–5s.

---

## 3. History Endpoints

### `GET /history?page=1&limit=20`
List all past queries, newest first.

- **Response `200`:**
```json
{
  "history": [
    {
      "query_id": "uuid",
      "query_text": "What are the responsibilities?",
      "answer_text": "The responsibilities include...",
      "search_mode": "semantic",
      "file_id": null,
      "sources": [ ... ],
      "cached": false,
      "status": "answered",
      "error_message": null,
      "created_at": "2026-04-01T09:00:00Z"
    }
  ],
  "total": 24,
  "page": 1,
  "limit": 20
}
```
- **Status values:** `answered` | `failed`

---

### `GET /history/{query_id}`
Full detail of one past query.

---

### `DELETE /history/{query_id}`
Remove a query from history.

- **Response `200`:** `{ "message": "Query deleted from history." }`

---

## 4. Health & Stats

### `GET /health`
Check all services. Call on Dashboard load and sidebar health indicator.

- **Response `200`:**
```json
{
  "status": "healthy",
  "services": {
    "api": "online",
    "celery": "online",
    "minio": "online",
    "postgresql": "online",
    "elasticsearch": "online",
    "redis": "online"
  },
  "checked_at": "2026-04-01T09:00:00Z"
}
```
- **`status`:** `"healthy"` (all core services online) or `"degraded"`

---

### `GET /stats`
Dashboard statistics.

- **Response `200`:**
```json
{
  "total_documents": 10,
  "indexed_documents": 8,
  "failed_documents": 1,
  "queries_today": 5,
  "total_queries": 42,
  "recent_documents": [ ... ],
  "recent_queries": [ ... ]
}
```

---

## 5. Settings Endpoints

### `GET /settings`
Get current runtime configuration.

- **Response `200`:**
```json
{
  "llm": {
    "provider": "openrouter",
    "model": "google/gemini-2.0-flash-exp:free",
    "api_key": null,
    "base_url": "https://openrouter.ai/api/v1"
  },
  "search": {
    "default_mode": "semantic",
    "top_k": 20,
    "reranker_top_n": 5
  },
  "cache": {
    "enabled": true,
    "ttl_seconds": 3600
  },
  "embedding_model": "BAAI/bge-large-en-v1.5"
}
```
> Note: `api_key` is never returned in GET — write-only.

---

### `PUT /settings`
Update configuration. Send only the fields you want to change.

- **Request (partial update example):**
```json
{
  "llm": {
    "provider": "openrouter",
    "model": "meta-llama/llama-3.1-8b-instruct:free",
    "api_key": "sk-or-..."
  }
}
```
- **Supported providers:** `openrouter` | `openai` | `anthropic` | `ollama`
- **Response `200`:** Updated settings object

---

### `POST /settings/cache/clear`
Flush all Redis query cache entries.

- **Response `200`:** `{ "message": "Cleared 12 cached query result(s)." }`

---

## Frontend Notes

### Status Badge Colors (Documents)
| Status | Color |
|---|---|
| `pending` | Gray |
| `extracting` | Blue |
| `chunking` | Blue |
| `embedding` | Amber/Yellow |
| `indexed` | Green |
| `failed` | Red |

### Search Mode Toggle (Chat)
- Two options only: **Semantic** (default) and **Keyword**
- Semantic = vector similarity (better for conceptual questions)
- Keyword = BM25 full-text (better for exact term lookup)

### Polling Strategy (Upload Flow)
```
Upload → status: pending
Poll /status every 4s
→ extracting (show progress step 1)
→ chunking   (show progress step 2)
→ embedding  (show progress step 3 — warn: first time takes longer)
→ indexed    (stop polling, show success)
→ failed     (stop polling, show error_message)
```

---

## Change Log

| Date | Change |
|---|---|
| 2026-03-13 | v1.0 — Initial registry |
| 2026-04-01 | v2.0 — Updated to match actual implementation: removed hybrid search, fixed ES references (OpenSearch→Elasticsearch), corrected response shapes, added frontend notes |
