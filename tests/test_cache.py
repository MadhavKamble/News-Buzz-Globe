from datetime import UTC, datetime

from backend.app.cache import EventsCache, events_cache_key

T = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)


class TestEventsCacheKey:
    def base_key(self):
        return events_cache_key("1,2,3,4", T, T, T, ["04"], ["protest"], 500)

    def test_deterministic(self):
        assert self.base_key() == self.base_key()

    def test_every_parameter_changes_the_key(self):
        # Regression guard: omitting any response-affecting param from the
        # key would serve stale results when that filter is toggled.
        base = self.base_key()
        variants = [
            events_cache_key("9,2,3,4", T, T, T, ["04"], ["protest"], 500),  # bbox
            events_cache_key("1,2,3,4", None, T, T, ["04"], ["protest"], 500),  # start
            events_cache_key("1,2,3,4", T, None, T, ["04"], ["protest"], 500),  # end
            events_cache_key("1,2,3,4", T, T, None, ["04"], ["protest"], 500),  # at
            events_cache_key("1,2,3,4", T, T, T, ["05"], ["protest"], 500),  # category
            events_cache_key("1,2,3,4", T, T, T, None, ["protest"], 500),  # no category
            events_cache_key("1,2,3,4", T, T, T, ["04"], ["conflict"], 500),  # theme
            events_cache_key("1,2,3,4", T, T, T, ["04"], None, 500),  # no theme
            events_cache_key("1,2,3,4", T, T, T, ["04"], ["protest"], 100),  # limit
        ]
        assert len({base, *variants}) == len(variants) + 1

    def test_filter_order_does_not_split_cache(self):
        a = events_cache_key(None, None, None, None, ["04", "14"], ["a", "b"], 500)
        b = events_cache_key(None, None, None, None, ["14", "04"], ["b", "a"], 500)
        assert a == b


class FakeRedis:
    def __init__(self, fail=False):
        self.store = {}
        self.fail = fail
        self.gets = 0
        self.sets = 0

    def get(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        self.gets += 1
        return self.store.get(key)

    def setex(self, key, ttl, value):
        if self.fail:
            raise ConnectionError("redis down")
        self.sets += 1
        self.store[key] = value


class TestEventsCache:
    def test_miss_then_hit(self):
        cache = EventsCache(client=FakeRedis())
        assert cache.get_json("k") is None
        cache.set_json("k", {"a": 1})
        assert cache.get_json("k") == {"a": 1}

    def test_redis_down_degrades_to_miss(self):
        cache = EventsCache(client=FakeRedis(fail=True))
        assert cache.get_json("k") is None
        cache.set_json("k", {"a": 1})  # must not raise
        assert cache.get_json("k") is None
