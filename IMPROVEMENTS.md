# IMPROVEMENTS & KNOWN ISSUES
Tracked items to address in future sessions.
Status: `[ ]` todo | `[/]` in progress | `[x]` done

---

## 🔧 Performance

### [ ] Preload ML models at uvicorn startup
**Issue:** Both `bge-large-en-v1.5` (embedding) and `bge-reranker-base` (reranker)
load lazily on first use in the uvicorn process. This means the **first query always
blocks for model load time** (~30–60 seconds after the download is cached).

**Root cause:** Celery and uvicorn are separate OS processes. Each loads models into
its own RAM independently. Disk cache (`~/.cache/huggingface/`) is shared, so files
are not re-downloaded — but in-memory loading still happens per-process.

**Fix:** In `app/main.py` lifespan startup, call `get_embedder()` and `get_reranker()`
so both models are warm before the first request hits.

```python
# In lifespan startup:
from app.services.embedding import get_embedder
from app.services.reranker import get_reranker
get_embedder()   # warm embedding model
get_reranker()   # warm reranker model
```

**Impact:** First query will respond in 2–5 seconds instead of 30–120 seconds.

---

## 🔧 Chunking

### [ ] Suppress tokenizer warning: "Token indices sequence length > 512"
**Issue:** When the chunker calls `tokenizer.encode(full_parent_text)` to measure
token count before splitting, HuggingFace tokenizer warns that the sequence exceeds
the model's max of 512. This is benign (we're using the tokenizer as a ruler, not
for inference), but it pollutes logs.

**Fix:** Suppress the warning by passing `max_length` and `truncation=False`
explicitly, or use `tokenizer(text, add_special_tokens=False).input_ids` and
suppress the specific transformers warning via `logging` filters.

---

## 🔧 Architecture

### [ ] Consider shared model server (future)
**Issue:** If both uvicorn and multiple Celery workers each hold `bge-large` in RAM,
total RAM usage multiplies (each instance = ~1.5GB RAM).

**Fix options:**
- Use a dedicated embedding microservice (e.g., `infinity-emb` or `text-embeddings-inference`)
  that uvicorn and Celery both call via HTTP
- Or run Celery with `--concurrency=1` (already done via `--pool=solo`) to limit to one worker

**Priority:** Low — only relevant when scaling beyond 1 worker.

---

## 🔧 API / UX

### [ ] Add Swagger `file_id` default as `null`
**Issue:** Swagger UI shows a placeholder UUID for `file_id` in the query body, which
confuses users into sending an invalid file_id.

**Fix:** Make `file_id` optional with `default=None` in the Pydantic schema (already
done) and add a Swagger example showing it omitted.

---
