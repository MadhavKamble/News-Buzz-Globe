"""Redis cache in front of /events.

The cache key is a hash over **every** query parameter that affects the
response — bounding box, start, end, reference time (at), category codes,
theme keys, and limit. Categories/themes are sorted so parameter order can't
split or alias entries; omitting any of these from the key would serve stale
results when a user toggles that filter.

Degrades gracefully: if Redis is down or absent, every lookup is a miss and
writes are dropped (logged once), so the API keeps serving from Postgres.
"""

import hashlib
import json
import os
from datetime import datetime

from common.logging_config import get_logger

logger = get_logger("backend.cache")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = int(os.environ.get("EVENTS_CACHE_TTL", "120"))
KEY_PREFIX = "nbg:events:"
CHAT_KEY_PREFIX = "nbg:chat:"
CHAT_CACHE_TTL_SECONDS = int(os.environ.get("CHAT_CACHE_TTL", "300"))


def chat_cache_key(query: str) -> str:
    """Deterministic key for a /chat query, same hashing pattern as events."""
    digest = hashlib.sha256(query.strip().encode()).hexdigest()
    return CHAT_KEY_PREFIX + digest


def events_cache_key(
    bbox: str | None,
    start: datetime | None,
    end: datetime | None,
    at: datetime | None,
    categories: list[str] | None,
    themes: list[str] | None,
    limit: int,
) -> str:
    """Deterministic key covering all response-affecting parameters."""
    payload = {
        "bbox": bbox,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "at": at.isoformat() if at else None,
        "categories": sorted(categories) if categories else [],
        "themes": sorted(themes) if themes else [],
        "limit": limit,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    return KEY_PREFIX + digest


class EventsCache:
    """Thin JSON get/set wrapper that never raises toward the API."""

    def __init__(self, client=None):
        self._client = client
        self._warned = False

    def _redis(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(
                REDIS_URL,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
                decode_responses=True,
            )
        return self._client

    def get_client(self):
        """Expose the underlying Redis client for callers needing raw ops
        beyond get/set (e.g. the /chat rate limiter's INCR/EXPIRE)."""
        return self._redis()

    def _warn_once(self, exc: Exception) -> None:
        if not self._warned:
            logger.warning(
                "redis unavailable; serving uncached", extra={"error": str(exc)[:200]}
            )
            self._warned = True

    def get_json(self, key: str) -> dict | None:
        try:
            raw = self._redis().get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001 - any cache failure means "miss"
            self._warn_once(exc)
            return None

    def set_json(self, key: str, value: dict, ttl: int = CACHE_TTL_SECONDS) -> None:
        try:
            self._redis().setex(key, ttl, json.dumps(value))
            self._warned = False
        except Exception as exc:  # noqa: BLE001
            self._warn_once(exc)
