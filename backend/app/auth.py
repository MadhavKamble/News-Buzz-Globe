"""JWT auth + sliding-window rate limiting, scoped to /chat only.

This is a demo auth flow (no password — /auth/token issues a token for any
user_id) meant to show the JWT mechanics, not to gate real user data. Every
other endpoint in the API stays public.
"""

import os
import time
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from common.logging_config import get_logger

logger = get_logger("backend.auth")

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_KEY_TTL_SECONDS = 90

_bearer_scheme = HTTPBearer()


def generate_token(user_id: str, expiry_hours: float = JWT_EXPIRY_HOURS) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=expiry_hours)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid token payload")
    return user_id


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency: validates the Authorization: Bearer <token> header."""
    return verify_token(credentials.credentials)


def check_rate_limit(user_id: str, redis_client) -> None:
    """Sliding-ish window: 10 requests per calendar minute per user_id.

    Degrades open (allows the request) if Redis is unreachable, matching this
    project's existing cache-failure philosophy (see cache.py) — a rate
    limiter must not be a new single point of failure for /chat.
    """
    current_minute = int(time.time() // 60)
    key = f"ratelimit:{user_id}:{current_minute}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, RATE_LIMIT_KEY_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - fail open, never break /chat
        logger.warning("redis unavailable; skipping rate limit", extra={"error": str(exc)[:200]})
        return
    if count > RATE_LIMIT_PER_MINUTE:
        retry_after = 60 - int(time.time() % 60)
        raise HTTPException(
            status_code=429,
            detail={"error": "rate limit exceeded", "retry_after": retry_after},
        )
