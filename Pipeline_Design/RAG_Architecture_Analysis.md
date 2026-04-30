# RAG Pipeline – Architecture Analysis & Implementation Plan

**Document Type:** Technical Architecture Reference
**Version:** 2.2
**Scope:** Final architecture decisions, pipeline design, data flow, and implementation plan for the RAG system.

> This document supersedes v2.1. It reflects all architecture decisions made by the project owner and is the single source of truth for implementation.

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [High-Level Pipeline Overview](#2-high-level-pipeline-overview)
3. [Storage Architecture](#3-storage-architecture)
4. [Stage-by-Stage Pipeline Breakdown](#4-stage-by-stage-pipeline-breakdown)
   - [Stage 1 — Document Ingestion](#stage-1--document-ingestion)
   - [Stage 2 — Data Extraction](#stage-2--data-extraction)
   - [Stage 3 — Hierarchical Chunking (Parent-Child)](#stage-3--hierarchical-chunking-parent-child)
   - [Stage 4 — Embedding](#stage-4--embedding)
   - [Stage 5 — Storage](#stage-5--storage)
   - [Stage 6 — Query & Retrieval](#stage-6--query--retrieval)
   - [Stage 7 — Reranking](#stage-7--reranking)
   - [Stage 8 — LLM Answer Generation](#stage-8--llm-answer-generation)
5. [Complete Data Flow](#5-complete-data-flow)
6. [Database Schema](#6-database-schema)
7. [API Design](#7-api-design)
8. [Technology Stack](#8-technology-stack)
9. [Implementation Phases](#9-implementation-phases)

---

## 1. What This System Does

This is a **document-understanding Retrieval Augmented Generation (RAG) system**.

In plain terms:
- A user uploads a PDF or Word document.
- The system reads and understands the document — including text, tables, and scanned pages.
- It breaks the content into structured, searchable pieces.
- It converts those pieces into mathematical representations (vectors/embeddings).
- When a user asks a question in plain English, the system finds the most relevant pieces from the documents.
- It hands those relevant pieces to an LLM (language model) which generates a grounded, cited answer.

**The system never makes up information** — every answer is grounded in the actual content of uploaded documents.

**Core design principles:**
- **Privacy-first** — document data stays inside controlled infrastructure by default.
- **API-first** — every pipeline stage is exposed as a function/API endpoint, making it easy to debug, swap, or test individual parts.
- **Self-hostable** — embedding models, search engine, and LLM can all run locally.
- **Pluggable** — the LLM and embedding model can be swapped without changing pipeline logic.

---

## 2. High-Level Pipeline Overview

The pipeline is divided into two distinct flows:

### Ingestion Flow (when a document is uploaded)

```
User Uploads Document (PDF or DOCX)
        │
        ▼
[API Layer] — POST /documents/upload
        │
        ├──► MinIO          → Stores raw file, returns file_id
        │
        └──► PostgreSQL     → Registers document (status = 'pending')
                │
                ▼
        [Celery Task Queue] → Async worker picks up job
                │
                ▼
        [Stage 1] Extraction
            PDF  → pdfplumber (text + tables) + PyMuPDF (images)
            DOCX → python-docx (text + tables directly)
            Note: Scanned PDFs (OCR) are not supported in Phase 1
                │
                ▼
        [Stage 2] Hierarchical Chunking (Parent-Child)
            Parent chunks → large context units (stored in PostgreSQL)
            Child chunks  → small precise retrieval units (stored in PostgreSQL + indexed in Elasticsearch)
                │
                ▼
        [Stage 3] Embedding
            Each child chunk → bge-large-en-v1.5 → 1024-dim vector
            Indexed into Elasticsearch
                │
                ▼
        Document status = 'indexed' ✓
```

### Query Flow (when a user asks a question)

```
User Submits Question
        │
        ▼
[API Layer] — POST /query
        │
        ▼
Redis cache check → HIT? Return cached answer immediately
                  → MISS? Continue
        │
        ▼
Query is embedded → bge-large-en-v1.5 → query vector
        │
        ▼
Elasticsearch Search (user selects mode):
    Keyword Mode  → BM25 full-text search on chunk_text
    Semantic Mode → kNN ANN search on embedding vectors
        │
        ▼
Top-20 Child Chunk IDs returned
        │
        ▼
PostgreSQL lookup → resolve child_chunk_ids → parent_chunk_ids → fetch parent chunk texts
        │
        ▼
Reranker (bge-reranker-base) → scores (Query vs each Parent Chunk) → Top-5
        │
        ▼
LLM (OpenRouter — pluggable) → Query + Top-5 Parent Chunks → Answer
        │
        ▼
Answer + Source Citations → Redis cache write → Response to User
```

---

## 3. Storage Architecture

Four storage systems, each with a distinct and non-overlapping responsibility:

| Store | Type | Role | What It Holds |
|---|---|---|---|
| **MinIO** | Object Storage | Raw file dump | Original uploaded files (PDF, DOCX), referenced by `file_id` |
| **PostgreSQL** | Relational DB | Metadata registry | Document status, parent chunks (full text), child chunks (text, token count) |
| **Elasticsearch** | Search Engine | Vector + keyword index | Child chunk embeddings (1024-dim) + BM25 text index for keyword search |
| **Redis** | Cache + Queue | Celery broker + query cache | Async task queue + cached query results keyed by query hash |

> **Critical rule:** Embeddings (vectors) are **never stored in PostgreSQL**. They live exclusively in Elasticsearch.
>
> **Critical rule:** PostgreSQL is **never queried for search**. It is only used to look up metadata after Elasticsearch returns chunk IDs.

---

## 4. Stage-by-Stage Pipeline Breakdown

---

### Stage 1 — Document Ingestion

**What happens here:** The user's file is received, stored, and registered. The async processing pipeline is triggered.

**Accepted formats:** PDF (`.pdf`), Word (`.docx`)

**Step-by-step:**

1. User uploads a file via `POST /documents/upload` (multipart/form-data).
2. The API validates the file type — only `.pdf` and `.docx` are accepted. Anything else → 400 error.
3. The raw file is uploaded to **MinIO** in the bucket `raw-documents/` under the path `{file_id}/{original_filename}`.
4. MinIO stores the file and the full object path (`minio_path`) is recorded.
5. A record is inserted into the **PostgreSQL `documents` table** with:
   - `file_id` (UUID, generated)
   - `filename`
   - `file_type` (`pdf` or `docx`)
   - `minio_path`
   - `status = 'pending'`
6. The HTTP response returns immediately with `file_id` and `status = 'pending'`. **The client does not wait for processing.**
7. A **Celery task** is enqueued in Redis — the async worker takes over from here.
8. The worker updates the document's `status` field in PostgreSQL at each stage: `pending → extracting → chunking → embedding → indexed` (or `failed` if an error occurs).

**Why async?** Document processing can take seconds to minutes depending on file size and whether OCR is needed. Blocking the HTTP request would make the API feel broken. Celery decouples upload from processing.

---

### Stage 2 — Data Extraction

**What happens here:** The raw file is read and all meaningful content is pulled out — text, tables, OCR text, and images. The output is a structured `ExtractedDocument` object that the chunker receives.

**DOCX files** are handled directly — no conversion to PDF:
- `python-docx` reads the Word file natively, preserving headings, paragraph structure, and tables.
- This avoids the data loss that happens when converting DOCX → PDF.

**Phase 1 supports only born-digital PDFs** (PDFs where text is selectable/copyable). Scanned PDFs require OCR which is deferred to Phase 2.

**PDF files** go through two extraction passes:

#### Pass 1: Selectable Text (pdfplumber)
- If the PDF contains embedded digital text (born digital, not scanned), `pdfplumber` extracts it page by page.
- Output: a string of text per page, with page number attached.
- This is the fastest and highest-quality extraction path.
- If a page has no selectable text (scanned page), it is **skipped in Phase 1** with a log warning.

#### Pass 2: Table Extraction (pdfplumber)
- `pdfplumber` also detects and extracts tables from PDFs.
- Each extracted table is converted to a **Markdown table format** (`| col1 | col2 |`) so it can be chunked and embedded as text like any other content.
- Tables get labelled with `chunk_type = 'table'` so they can be filtered or weighted differently in retrieval.

#### Pass 3: Image Extraction (PyMuPDF) — Phase 1 metadata only
- `PyMuPDF` detects embedded images but does not process them in Phase 1.
- In Phase 3, a **Vision Language Model (VLM)** will be plugged in to generate textual captions for images, which will enter the chunking pipeline as `chunk_type = 'image_caption'`.

**Output of Stage 2:**

```python
ExtractedDocument(
    file_id = "uuid",
    pages = [
        PageContent(
            page_number = 1,
            text_content = "...",           # from pdfplumber or python-docx
            table_content = [               # list of markdown tables
                "| Col1 | Col2 |\n|---|---|\n| ... |"
            ],
            # image_caption → Phase 3 (VLM)
        ),
        ...
    ]
)
```

All content types from a single page are tagged by source (`text`, `table`) so the chunker and storage layer always know what kind of content each chunk came from.

---

### Stage 3 — Hierarchical Chunking (Parent-Child)

**What happens here:** Extracted text is split into a two-level hierarchy of chunks. This is the most important design decision in the pipeline.

**Why Hierarchical (Parent-Child)?**

Two competing needs exist in RAG:

| Need | Requirement |
|---|---|
| **Precise retrieval** | Chunks must be small and focused — a tiny, specific passage is easier to match to a query |
| **Rich generation context** | The LLM needs enough surrounding context to give a complete, meaningful answer |

A single chunk size cannot satisfy both. The solution is two levels:

- **Child chunks** = small, precise. Used for search. The ANN (vector search) runs against these.
- **Parent chunks** = large context. Used for generation. After retrieval finds the right child chunk, the system fetches the parent chunk and gives that to the LLM.

**Parent Chunk Sizing:**

Parent chunks are created at **semantic/structural boundaries** — paragraph groups, heading sections, or logical document sections. A parent chunk targets **~800–1,000 tokens** of content (roughly 550–700 words).

**Why 800–1,000 tokens (not larger)?**

When the top-5 parent chunks are assembled into the LLM prompt:
```
5 parents × 900 tokens avg  = 4,500 tokens  (context)
System prompt               =   300 tokens
User query                  =    50 tokens
Expected LLM response       =   500 tokens
─────────────────────────────────────────────
Total prompt size           ≈ 5,350 tokens
```
This is well within the context window of every free OpenRouter model. Larger parents would push the total over 10,000 tokens and dilute the LLM's focus.

Parent chunks are stored in the **PostgreSQL `parent_chunks` table** and are **never indexed in Elasticsearch**.

**Child Chunk Sizing — How the Tokenizer Acts as the Ruler:**

Child chunks must be under **512 tokens** (the hard limit of `bge-large-en-v1.5`).

The tokenizer (`AutoTokenizer` from HuggingFace for `BAAI/bge-large-en-v1.5`) is used **directly inside the chunker as the measurement tool**.

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

def chunk_to_fit(text: str, target_tokens: int = 400, hard_limit: int = 500):
    tokens = tokenizer.encode(text)
    if len(tokens) <= target_tokens:
        return [text]  # fits in one child chunk
    # Otherwise: split into overlapping windows of target_tokens
    chunks = []
    stride = target_tokens - 20  # 20-token overlap between consecutive child chunks
    for start in range(0, len(tokens), stride):
        window = tokens[start : start + target_tokens]
        chunks.append(tokenizer.decode(window))
    return chunks
```

- **Target: 400 tokens** per child chunk (~270–300 words in English).
- **Hard cap: 500 tokens** (below the 512 model limit — gives a 12-token safety margin).
- **Overlap: ~20 tokens** between consecutive child chunks so context is not lost at boundaries.

**How Parent and Child Chunks Are Numbered:**

`chunk_number` = the parent's sequential position within the document (1, 2, 3…).
`child_number` = the child's sequential position within its own parent (1, 2… — resets per parent).

Both use UUIDs as their actual database primary keys. The numbers (`chunk_number`, `child_number`) are human-readable sequence fields used for ordering, display, and citation (e.g. "Page 3, Chunk 2, Section 1").

```
Document: annual_report.pdf  (file_id = "abc-123")

├── Parent Chunk  [chunk_number=1, page=1]  (~900 tokens)
│       "Introduction: This report covers the fiscal year 2025..."
│   ├── Child Chunk  [child_number=1]  (~400 tokens)
│   │       "Introduction: This report covers the fiscal year 2025..."
│   └── Child Chunk  [child_number=2]  (~400 tokens)
│           "...the key findings from Q1 to Q4 are summarised below."
│
├── Parent Chunk  [chunk_number=2, page=2]  (~900 tokens)
│       "Revenue grew by 18% driven by..."
│   ├── Child Chunk  [child_number=1]  (~400 tokens)
│   │       "Revenue grew by 18% driven by strong APAC performance..."
│   └── Child Chunk  [child_number=2]  (~400 tokens)
│           "...primarily in Singapore and Mumbai markets."
```

Each parent has **~2 children** on average (900 token parent ÷ 400 token child, with 20-token overlap).

**Chunk Metadata Assembly:**

```
parent_chunk:
    parent_chunk_id  → UUID  (primary key)
    file_id          → links back to MinIO object and documents table
    page_number      → page this parent chunk starts on
    chunk_number     → sequence position within the document (1, 2, 3...)
    chunk_text       → the full context text (~800-1,000 tokens)
    chunk_type       → 'text' | 'table'   (Phase 3 adds: 'image_caption')
    metadata         → JSONB (source filename, tags, etc.)

child_chunk:
    child_chunk_id   → UUID  (primary key)
    parent_chunk_id  → foreign key to its parent
    file_id          → foreign key to documents
    page_number      → page this child chunk is on
    child_number     → sequence within its parent (1, 2... resets per parent)
    chunk_text       → the small precise retrieval text (~400 tokens)
    token_count      → exact token count (measured by tokenizer at creation)
    metadata         → JSONB
```

**PostgreSQL write happens here** — both `parent_chunks` and `child_chunks` tables are populated.

---

### Stage 4 — Embedding

**What happens here:** Each child chunk is converted into a 1024-dimensional float vector that captures its semantic meaning. This vector is what enables semantic (meaning-based) search.

**Embedding Model: `BAAI/bge-large-en-v1.5`**

- Self-hosted via HuggingFace Transformers — runs on the same server, no external API call.
- Produces a **1024-dimensional dense vector** per chunk.
- Hard token limit: 512 tokens. Child chunks are already guaranteed to be under this (from Stage 3).
- The same model is used at query time to embed the user's question — this is essential.

**Pluggable Interface:**

The embedding model is accessed through a common interface so it can be swapped without changing any pipeline logic.

> ⚠️ **Critical constraint:** If you change the embedding model, **all documents must be re-indexed**. Old embeddings in Elasticsearch are incompatible with the new model's vector space.

**What goes into Elasticsearch:**

For each child chunk, the following document is indexed:

```json
{
  "child_chunk_id":  "uuid",
  "parent_chunk_id": "uuid",
  "file_id":         "uuid",
  "chunk_text":      "The actual text of this small child chunk...",
  "embedding":       [0.023, -0.17, 0.041, ...],
  "page_number":     3,
  "chunk_type":      "text",
  "metadata": {
    "source": "annual_report.pdf",
    "tags": []
  }
}
```

---

### Stage 5 — Storage

**What happens here:** The chunking and embedding outputs are persisted into their correct stores. This finalizes the ingestion pipeline.

| What | Goes Where | How |
|---|---|---|
| Raw file | MinIO | Already done at Stage 1 |
| Document record + status | PostgreSQL `documents` | Updated at each stage transition |
| Parent chunks (full text) | PostgreSQL `parent_chunks` | Batch INSERT after chunking |
| Child chunks (small text + token count) | PostgreSQL `child_chunks` | Batch INSERT after chunking |
| Child chunk embeddings + metadata | Elasticsearch index | Bulk index after embedding |

When all items are indexed in Elasticsearch, the worker sets `documents.status = 'indexed'` in PostgreSQL.

---

### Stage 6 — Query & Retrieval

**What happens here:** A user's natural language question is searched against the indexed documents to find the most relevant passages.

**Step 1 — Redis Cache Check**

Before any computation, a hash of the query string (+ any filters like file_id or search mode) is checked against Redis.

**Step 2 — Query Embedding**

The user's query text is passed through **the same embedding model** used during ingestion (`bge-large-en-v1.5`).

**Step 3 — Elasticsearch Search**

The user selects one of two search modes:

#### Keyword Mode (BM25)
- Traditional full-text search using Elasticsearch's inverted index.
- Scores chunks based on **term frequency** and **inverse document frequency**.

#### Semantic Mode (kNN / ANN)
- Vector similarity search using the query embedding.
- Finds chunks whose meaning is close to the query's meaning, even if no exact words match.

**Both modes search the child chunks in Elasticsearch and return the top-20 child chunk IDs and their scores.**

**Step 4 — Child → Parent Resolution**

The top-20 child chunk IDs returned by Elasticsearch are used to look up their parent chunks in PostgreSQL. This is the key mechanism of Parent-Child chunking: **search small (child), retrieve large (parent)**.

---

### Stage 7 — Reranking

**What happens here:** The retrieved parent chunks are rescored for relevance against the user's exact query.

**Reranker Model: `BAAI/bge-reranker-base`**

- Self-hosted, fast.
- Takes as input: `(query, chunk_text)` pairs.
- Outputs: a relevance score per pair.
- Runs only against the top parent chunks from retrieval (not the full index) — negligible compute cost.

**Process:**

```
Input: query + N parent chunks (from Stage 6, typically 5–15 unique parents from the top-20 children)

For each parent chunk:
    score = reranker(query, parent_chunk.chunk_text)

Sort by score (descending)
Take top-5 parent chunks
```

---

### Stage 8 — LLM Answer Generation

**What happens here:** The top-5 parent chunks are combined with the user's question and sent to an LLM, which generates a grounded, natural language answer.

**LLM Provider: OpenRouter (default, pluggable)**

OpenRouter is used as the default because it is a **unified API gateway** — one API key gives access to models from OpenAI, Anthropic, Google, Mistral, Meta, and many others.

**Prompt Construction:**

```
SYSTEM:
You are a document assistant. Answer the user's question using ONLY the context
provided below. If the answer is not in the context, say so clearly.
Do not make up information.

CONTEXT:
[Parent Chunk 1 — source: annual_report.pdf, page 4]
"...full text of parent chunk 1..."

... (up to 5 parent chunks)

USER:
What are the main findings of the report?
```

---

## 5. Complete Data Flow

### Ingestion Flow

```
[User] POST /documents/upload (multipart PDF or DOCX)
    │
    ├──► MinIO: PUT raw-documents/{file_id}/{filename}
    │
    └──► PostgreSQL: INSERT INTO documents (file_id, filename, file_type, minio_path, status='pending')
    │
    [Celery Worker picks up task]
    │
    ├── [Extraction Module]
    │       PDF:  pdfplumber → text, tables
    │       DOCX: python-docx → text, tables
    │
    ├── [Chunking Module — Hierarchical Parent-Child]
    │       → Parent chunks created (~800-1000 tokens)
    │       → Child chunks split from each parent (target 400, cap 500 tokens)
    │
    ├── [Embedding Module]
    │       → bge-large-en-v1.5 embeds each child chunk → 1024-dim vector
    │       → Elasticsearch: BULK INDEX { child_chunk_id, parent_chunk_id, chunk_text, embedding, metadata }
    │
    └── PostgreSQL: UPDATE documents SET status='indexed'
```

### Query Flow

```
[User] POST /query { query: "...", mode: "semantic"|"keyword", file_id: null|"uuid" }
    │
    ├── Redis: GET cache[hash(query + mode + file_id)]
    │
    ├── [Embedding Module]
    │       query_vector = bge-large-en-v1.5.embed(query)
    │
    ├── [Elasticsearch Search]
    │       Keyword:  BM25 match on chunk_text → top-20 child chunks
    │       Semantic: kNN ANN on embedding → top-20 child chunks
    │
    ├── [PostgreSQL Lookup — Child → Parent Resolution]
    │       SELECT chunk_text, page_number, file_id
    │       FROM parent_chunks WHERE parent_chunk_id IN (...)
    │
    ├── [Reranker — bge-reranker-base]
    │       Scores query vs each parent chunk → Top-5 reranked
    │
    ├── [LLM — OpenRouter (or configured provider)]
    │       response = LLM.generate(prompt)
    │
    └── Response: { query_id, answer, sources, cached: false }
```

---

## 6. Database Schema

### MinIO — Object Storage

```
Bucket: raw-documents/
    └── {file_id}/
            └── {original_filename}
```

### PostgreSQL — Relational Schema

```sql
CREATE TABLE documents (
    file_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    filename      VARCHAR     NOT NULL,
    file_type     VARCHAR     NOT NULL,
    minio_path    VARCHAR     NOT NULL,
    status        VARCHAR     NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE parent_chunks (
    parent_chunk_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id          UUID        REFERENCES documents(file_id) ON DELETE CASCADE,
    page_number      INTEGER,
    chunk_number     INTEGER,
    chunk_text       TEXT        NOT NULL,
    chunk_type       VARCHAR,
    metadata         JSONB       DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE child_chunks (
    child_chunk_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_chunk_id  UUID        REFERENCES parent_chunks(parent_chunk_id) ON DELETE CASCADE,
    file_id          UUID        REFERENCES documents(file_id) ON DELETE CASCADE,
    page_number      INTEGER,
    child_number     INTEGER,
    chunk_text       TEXT        NOT NULL,
    token_count      INTEGER,
    metadata         JSONB       DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

### Elasticsearch Index Mapping

```json
{
  "mappings": {
    "properties": {
      "child_chunk_id":  { "type": "keyword" },
      "parent_chunk_id": { "type": "keyword" },
      "file_id":         { "type": "keyword" },
      "chunk_text":      { "type": "text", "analyzer": "english" },
      "embedding": {
        "type":       "dense_vector",
        "dims":       1024,
        "index":      true,
        "similarity": "cosine"
      }
    }
  }
}
```

---

## 7. API Design

All pipeline logic is exposed as individual API functions/endpoints.

### Document / Ingestion Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/documents/upload` | Upload a new document (triggers async pipeline) |
| `GET` | `/documents` | List all documents with status and metadata |
| `DELETE` | `/documents/{file_id}` | Delete document + all chunks + MinIO file + Elasticsearch entries |

### Query Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/query` | Submit a query, returns answer + sources |

---

## 8. Technology Stack

| Component | Technology |
|---|---|
| **API Framework** | FastAPI (Python) |
| **Task Queue** | Celery + Redis |
| **Object Storage** | MinIO |
| **Relational DB** | PostgreSQL |
| **Search / Vector Store** | Elasticsearch |
| **PDF Text Extraction** | pdfplumber |
| **DOCX Extraction** | python-docx |
| **Embedding Model** | BAAI/bge-large-en-v1.5 |
| **Reranker** | BAAI/bge-reranker-base |
| **LLM (default)** | OpenRouter API |

---

## 9. Implementation Phases

### Phase 1 — Core MVP (Build First)

**Goal:** End-to-end pipeline working — upload a PDF or DOCX, process it, ask a question, get a grounded answer.

**Development Order (12-week plan):**

```
Week 1  → Docker Compose setup, PostgreSQL schema, Elasticsearch index mapping, MinIO bucket
Week 2  → FastAPI skeleton — all endpoints stubbed
Week 3  → Extraction Module (pdfplumber + python-docx)
Week 4  → Chunking Module (hierarchical parent-child, tokenizer-based sizing)
Week 5  → Embedding Module (bge-large-en-v1.5)
Week 6  → Elasticsearch Module (bulk index, keyword search, semantic search)
Week 7  → Celery task queue wiring + status tracking
Week 8  → Query Service (full pipeline: embed → search → resolve → rerank → LLM → respond)
Week 9  → End-to-end integration testing
Week 10 → Redis cache, LLM provider settings
Week 11 → React Frontend
Week 12 → Polish, error handling, documentation
```

### Phase 2 — Quality & Robustness

**Goal:** Improve reliability, coverage, and retrieval quality.

- Refine chunking at structural boundaries (headings, sections) for better parent chunk quality
- Add agentic chunking as an **opt-in** mode for specific document types (gated by config flag)
- Add metadata tag extraction (document-level: title, date, author) stored in `documents.metadata`
- Query filter enhancements — filter by date range, document type, tags
- Observability — structured logging (every pipeline stage logs input/output size, timing), basic error alerting
- Unit and integration test coverage for all modules

---

### Phase 3 — Advanced Features

**Goal:** Full production capability and self-sufficiency.

- **VLM Image Understanding** — plug in a multimodal model (e.g. LLaVA, Phi-3-Vision) to generate text captions for embedded images during extraction. Captions enter the chunking pipeline as `chunk_type = 'image_caption'`.
- **LLM Metadata Enrichment** — post-chunking LLM pass (small local model via Ollama) to generate per-document summaries and keyword tags. Stored as metadata. Improves filter-based retrieval.
- **Full Self-Hosted LLM** — Ollama with an open model (e.g. Llama 3.1 8B or Qwen 2.5) for complete data sovereignty — no document content ever leaves the server.
- **Multi-tenancy** — user/org isolation at the document and chunk level (each user sees only their own documents).
- **Evaluation Framework** — integrate RAGAS or similar to benchmark retrieval quality (precision, recall, faithfulness) against a test set.
- **Hybrid Search (RRF)** — combine BM25 + kNN scores using Reciprocal Rank Fusion as a third search mode, if evaluation shows it improves answer quality. Elasticsearch 8.8+ has native RRF support via `rank` clause.

---

*End of document — Version 2.0*
