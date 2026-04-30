"""
Embedding Service
Model: BAAI/bge-large-en-v1.5
Dims:  1024
- Self-hosted via sentence-transformers (wraps HuggingFace Transformers)
- Singleton pattern: loaded once, reused across all calls
- Used for both: indexing (child chunks) and querying (user queries)
"""
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)

_embedder: Optional[SentenceTransformer] = None


def get_embedder() -> SentenceTransformer:
    """
    Lazy singleton loader.
    First call downloads the model (~1.3GB) and loads it into memory.
    Subsequent calls return the cached instance instantly.
    """
    global _embedder
    if _embedder is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        logger.info("This may take a minute on first run (model download ~1.3GB)...")
        _embedder = SentenceTransformer(settings.embedding_model)
        logger.info(f"Embedding model loaded. Output dim: {_embedder.get_sentence_embedding_dimension()}")
    return _embedder


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    Embed a list of texts and return their 1024-dimensional vectors.
    Uses bge-large's recommended prefix for asymmetric retrieval:
    - Document chunks: no prefix (model handles this internally)
    - Queries: we prepend "Represent this sentence: " in embed_query()
    """
    embedder = get_embedder()
    embeddings = embedder.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,     # cosine similarity works correctly with L2-normalised vectors
        show_progress_bar=len(texts) > 50,
    )
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """
    Embed a single user query.
    BGE models use the instruction prefix for queries in asymmetric retrieval.
    """
    instruction = "Represent this sentence: "
    embedder = get_embedder()
    embedding = embedder.encode(
        instruction + query,
        normalize_embeddings=True,
    )
    return embedding.tolist()


def embed_chunks(chunk_texts: list[str]) -> list[list[float]]:
    """
    Embed document chunks (no query prefix — symmetric side).
    """
    return embed_texts(chunk_texts)
