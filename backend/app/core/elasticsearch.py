from elasticsearch import Elasticsearch
from app.core.config import settings
import logging
import urllib3

# Suppress SSL warnings in dev (verify_certs=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# ── Client ────────────────────────────────────────────────────────────────────

def _build_es_client() -> Elasticsearch:
    """
    Build Elasticsearch client.
    ES 8.x enables HTTPS + TLS by default.
    Use ELASTICSEARCH_URL=https://localhost:9200 in .env
    and ELASTICSEARCH_VERIFY_CERTS=false for local dev with self-signed certs.
    """
    kwargs = {
        "hosts": [settings.elasticsearch_url],
        "verify_certs": settings.elasticsearch_verify_certs,
        "ssl_show_warn": False,
    }
    if settings.elasticsearch_username and settings.elasticsearch_password:
        kwargs["basic_auth"] = (
            settings.elasticsearch_username,
            settings.elasticsearch_password,
        )
    return Elasticsearch(**kwargs)


es_client: Elasticsearch = _build_es_client()

# ── Index Mapping ─────────────────────────────────────────────────────────────

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "child_chunk_id":  {"type": "keyword"},
            "parent_chunk_id": {"type": "keyword"},
            "file_id":         {"type": "keyword"},
            "chunk_text": {
                "type":     "text",
                "analyzer": "english",    # BM25 with English stemming/stopwords
            },
            "embedding": {
                "type":       "dense_vector",
                "dims":       1024,
                "index":      True,
                "similarity": "cosine",   # cosine similarity for bge-large
            },
            "page_number": {"type": "integer"},
            "chunk_type":  {"type": "keyword"},
            "metadata":    {"type": "object", "enabled": True},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,          # single-node dev setup
    },
}


def ensure_index_exists() -> None:
    """Create the Elasticsearch index if it does not exist. Called at startup."""
    index = settings.elasticsearch_index
    try:
        if not es_client.indices.exists(index=index):
            es_client.indices.create(index=index, body=INDEX_MAPPING)
            logger.info(f"Elasticsearch index '{index}' created.")
        else:
            logger.info(f"Elasticsearch index '{index}' already exists.")
    except Exception as e:
        logger.error(f"Failed to ensure Elasticsearch index: {e}")
        raise


def delete_chunks_by_file(file_id: str) -> None:
    """Delete all child chunk documents from Elasticsearch for a given file_id."""
    es_client.delete_by_query(
        index=settings.elasticsearch_index,
        body={"query": {"term": {"file_id": file_id}}},
    )
