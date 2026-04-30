# RAG Pipeline – Database Schema & Data Flow

**Version:** 1.0

---

## Table of Contents

1. [Storage Components Overview](#1-storage-components-overview)
2. [MinIO (Object Storage)](#2-minio-object-storage)
3. [PostgreSQL Schema](#3-postgresql-schema)
4. [OpenSearch Index](#4-opensearch-index)
5. [Ingestion Data Flow](#5-ingestion-data-flow)
6. [Query Data Flow](#6-query-data-flow)
7. [Table Interaction Summary](#7-table-interaction-summary)

---

## 1. Storage Components Overview

| Store | Type | Purpose |
|---|---|---|
| **MinIO** | Object Storage | Raw uploaded files (PDF, DOCX) |
| **PostgreSQL** | Relational DB | File registry, pipeline status, chunk metadata |
| **OpenSearch** | Search Engine | Child chunk embeddings + keyword index |
| **Redis** | Cache / Queue | Celery task broker + query result cache |

> Embeddings are **never** stored in PostgreSQL. They live exclusively in OpenSearch.

---

## 2. MinIO (Object Storage)

MinIO is an S3-compatible blob store. Files are organized as:

```
Bucket: raw-documents/
  └── {file_id}/{original_filename}

Examples:
  raw-documents/3f7a1bc2-.../annual_report.pdf
  raw-documents/9a4c2de1-.../contract.docx
```

- One bucket (`raw-documents`) for all uploads
- Files keyed by `file_id` (UUID) to prevent name collisions
- The full object path is persisted in `documents.minio_path`

---

## 3. PostgreSQL Schema

### `documents` — File Registry

Created at upload time. Tracks each file through the entire pipeline.

```sql
CREATE TABLE documents (
    file_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename      VARCHAR     NOT NULL,
    file_type     VARCHAR     NOT NULL,  -- 'pdf' | 'docx'
    minio_path    VARCHAR     NOT NULL,  -- full object path in MinIO
    status        VARCHAR     NOT NULL DEFAULT 'pending',
    -- pending → extracting → chunking → embedding → indexed | failed
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

### `parent_chunks` — Large Context Units

Parent chunks are the full-context units sent to the LLM during generation.

```sql
CREATE TABLE parent_chunks (
    parent_chunk_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id          UUID REFERENCES documents(file_id) ON DELETE CASCADE,
    page_number      INTEGER,
    chunk_number     INTEGER,      -- sequence within document
    chunk_text       TEXT NOT NULL,
    chunk_type       VARCHAR,      -- 'text' | 'table' | 'ocr' | 'image_caption'
    metadata         JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_parent_chunks_file_id ON parent_chunks(file_id);
```

---

### `child_chunks` — Small Retrieval Units

Child chunks are derived from parent chunks. ANN vector search runs against these. They act as the bridge between OpenSearch results and parent chunk context.

```sql
CREATE TABLE child_chunks (
    child_chunk_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_chunk_id  UUID REFERENCES parent_chunks(parent_chunk_id) ON DELETE CASCADE,
    file_id          UUID REFERENCES documents(file_id) ON DELETE CASCADE,
    page_number      INTEGER,
    child_number     INTEGER,      -- sequence within parent chunk
    chunk_text       TEXT NOT NULL,
    token_count      INTEGER,
    metadata         JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_child_chunks_parent_id ON child_chunks(parent_chunk_id);
CREATE INDEX idx_child_chunks_file_id   ON child_chunks(file_id);
```

---

## 4. OpenSearch Index

Each indexed document represents one child chunk alongside its embedding vector.

```json
{
  "child_chunk_id":  "uuid",
  "parent_chunk_id": "uuid",
  "file_id":         "uuid",
  "chunk_text":      "...",
  "embedding":       [0.023, -0.17, "...  1024 dims"],
  "page_number":     3,
  "chunk_type":      "text",
  "metadata": {
    "source": "annual_report.pdf",
    "tags":   []
  }
}
```

**Required index settings:**
- `dense_vector` field → ANN (kNN) semantic search
- `text` field with BM25 analyzer → keyword search

---

## 5. Ingestion Data Flow

```
[User Uploads File]
        │
        ▼
   POST /upload
        │
        ├─► MinIO      → store raw file → returns minio_path
        │
        └─► PostgreSQL → INSERT INTO documents (status = 'pending')
                │
                ▼
      HTTP 200 returned immediately ←──────────────────────────────────┐
                │                                                       │
                ▼                                                       │
      [Async Celery Worker]                                             │
                │                                                       │
                ▼                                                       │
      status = 'extracting'                                             │
      Extraction Module:                                                │
        PDF  → pdfplumber (text + tables) + Tesseract (OCR)            │
        DOCX → python-docx (text + tables)                             │
                │                                                       │
                ▼                                                       │
      status = 'chunking'                                               │
      Chunking Module (Hierarchical Parent–Child):                      │
        → Parent chunks created                                         │
        → Child chunks split from each parent                           │
        → PostgreSQL: INSERT parent_chunks, child_chunks               │
                │                                                       │
                ▼                                                       │
      status = 'embedding'                                              │
      Embedding Module:                                                 │
        AutoTokenizer → token count check                              │
        bge-large-en-v1.5 → embedding vector per child chunk           │
        → OpenSearch: INDEX child chunk + embedding + metadata          │
                │                                                       │
                ▼                                                       │
      status = 'indexed' ─────────────────────────────────────────────┘
```

---

## 6. Query Data Flow

```
[User Submits Query]
        │
        ▼
   POST /query  { "query": "...", "mode": "semantic" | "keyword" }
        │
        ▼
   Redis cache check (query hash + filters)
   HIT  → return cached answer ──────────────────────────────────────┐
   MISS ↓                                                             │
        │                                                             │
        ▼                                                             │
   Embedding Model → query_vector                                     │
        │                                                             │
        ▼                                                             │
   OpenSearch search (user-selected mode):                            │
     Keyword  → BM25 full-text on chunk_text                         │
     Semantic → kNN ANN on embedding field                            │
   Returns: Top-20 child_chunk_ids                                    │
        │                                                             │
        ▼                                                             │
   PostgreSQL:                                                        │
     SELECT DISTINCT parent_chunk_id                                  │
     FROM child_chunks                                                │
     WHERE child_chunk_id IN (…top-20…)                              │
        │                                                             │
        ▼                                                             │
   PostgreSQL:                                                        │
     SELECT chunk_text, page_number, file_id                          │
     FROM parent_chunks                                               │
     WHERE parent_chunk_id IN (…resolved ids…)                        │
        │                                                             │
        ▼                                                             │
   Reranker (bge-reranker-base):                                      │
     Score query vs each parent chunk → Top-5                         │
        │                                                             │
        ▼                                                             │
   LLM (Ollama / OpenRouter / OpenAI / Gemini):                       │
     prompt = system_template + query + Top-5 parent chunk texts      │
        │                                                             │
        ▼                                                             │
   Answer + Citations → Redis cache write                             │
        │                                                             │
        ▼  ◄───────────────────────────────────────────────────────┘
   Response: { "answer": "...", "sources": [{ file_id, page_number, parent_chunk_id }] }
```

---

## 7. Table Interaction Summary

| Store | Written By | Read By | Purpose |
|---|---|---|---|
| **MinIO** | Ingestion API | Extraction Worker | Raw file blobs |
| **documents** | Ingestion API, Worker | Status API, Query Service | File registry + status tracking |
| **parent_chunks** | Chunking Worker | Query Service | Full context for LLM |
| **child_chunks** | Chunking Worker | Query Service (child → parent lookup) | Maps ANN hits to parent context |
| **OpenSearch** | Embedding Worker | Query Service (search) | Vector + keyword index |
| **Redis** | Query Service | Query Service | Result cache + task queue |

---

*End of document.*
