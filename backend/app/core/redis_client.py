import redis
from app.core.config import settings
import logging
import hashlib
import json
from typing import Optional, Any

logger = logging.getLogger(__name__)

# ── Client ────────────────────────────────────────────────────────────────────

redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,      # always return strings, not bytes
)


def ping_redis() -> bool:
    """Check if Redis is reachable."""
    try:
        return redis_client.ping()
    except Exception as e:
        logger.error(f"Redis ping failed: {e}")
        return False


# ── Query Cache ───────────────────────────────────────────────────────────────

def _cache_key(query: str, mode: str, file_id: Optional[str]) -> str:
    """Stable cache key from query parameters."""
    raw = f"{query}|{mode}|{file_id or 'all'}"
    return "rag:query:" + hashlib.sha256(raw.encode()).hexdigest()


def get_cached_query(query: str, mode: str, file_id: Optional[str]) -> Optional[dict]:
    """Return cached query result or None on cache miss."""
    key = _cache_key(query, mode, file_id)
    value = redis_client.get(key)
    if value:
        return json.loads(value)
    return None


def set_cached_query(
    query: str,
    mode: str,
    file_id: Optional[str],
    result: dict,
    ttl: int,
) -> None:
    """Cache a query result with a TTL in seconds."""
    key = _cache_key(query, mode, file_id)
    redis_client.setex(key, ttl, json.dumps(result))


def clear_all_query_cache() -> int:
    """Flush all RAG query cache entries. Returns the number of keys deleted."""
    keys = redis_client.keys("rag:query:*")
    if keys:
        return redis_client.delete(*keys)
    return 0
