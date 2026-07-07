import pytest
from fastapi import HTTPException

from backend.app.auth import check_rate_limit, generate_token, verify_token


class TestJWT:
    def test_generate_and_verify_token(self):
        token = generate_token("alice")
        assert verify_token(token) == "alice"

    def test_expired_token_raises_401(self):
        token = generate_token("alice", expiry_hours=-1)
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401


class FakeRedis:
    """Matches the FakeRedis convention in test_cache.py, extended with the
    INCR/EXPIRE ops the rate limiter needs."""

    def __init__(self):
        self.store = {}

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, ttl):
        pass


class TestRateLimit:
    def test_rate_limit_exceeded_raises_429(self):
        redis_client = FakeRedis()
        for _ in range(10):
            check_rate_limit("alice", redis_client)
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit("alice", redis_client)
        assert exc_info.value.status_code == 429
