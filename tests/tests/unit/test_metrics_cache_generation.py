"""Offline regression tests: cache invalidation must never scan Redis."""

import asyncio

import pytest

from kato.storage.metrics_cache import CachedMetricsCalculator, MetricsCacheManager


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.calls = []
        self.fail_get = False
        self.fail_set = False
        self.before_setex = None

    async def get(self, key):
        self.calls.append(("get", key))
        await asyncio.sleep(0)
        if self.fail_get:
            raise ConnectionError("test Redis unavailable")
        return self.values.get(key)

    async def set(self, key, value, nx=False):
        self.calls.append(("set", key))
        await asyncio.sleep(0)
        if self.fail_set:
            raise ConnectionError("test Redis unavailable")
        if nx and key in self.values:
            return None
        self.values[key] = value.encode("ascii")
        return True

    async def setex(self, key, ttl, value):
        self.calls.append(("setex", key))
        if self.before_setex is not None:
            hook, self.before_setex = self.before_setex, None
            await hook()
        self.values[key] = value.encode("ascii")
        self.ttls[key] = ttl
        return True

    async def keys(self, *args, **kwargs):
        raise AssertionError("Invalidation must not use KEYS")

    async def scan(self, *args, **kwargs):
        raise AssertionError("Invalidation must not scan the keyspace")

    async def delete(self, *args, **kwargs):
        raise AssertionError("Invalidation must not delete stored data")


def manager(redis=None):
    value = MetricsCacheManager(ttl=123)
    value.redis = redis if redis is not None else FakeRedis()
    return value


def test_cache_hit_and_ttl_are_preserved_without_reading_legacy_entries():
    async def run():
        cache = manager()
        legacy_key = cache._generate_cache_key("potential", state="A")
        cache.redis.values[legacy_key] = b"99.0"
        assert await cache.get_cached_metric("potential", state="A") is None
        assert await cache.cache_metric("potential", 0.25, state="A")
        assert await cache.get_cached_metric("potential", state="A") == 0.25
        assert list(cache.redis.ttls.values()) == [123]
        assert cache.redis.values[legacy_key] == b"99.0"
        assert cache.stats["hits"] == 1
        assert cache.stats["updates"] == 1
    asyncio.run(run())


@pytest.mark.parametrize("method", ["invalidate_pattern_metrics", "invalidate_all_metrics"])
def test_invalidation_is_one_command_and_preserves_existing_data(method):
    async def run():
        cache = manager()
        cache.redis.values["training:pattern:important"] = b"keep"
        assert await cache.cache_metric("potential", 0.25, state="A")
        before = dict(cache.redis.values)
        cache.redis.calls.clear()
        invalidate = getattr(cache, method)
        assert await invalidate(*(["pattern-A"] if method == "invalidate_pattern_metrics" else [])) == 1
        assert cache.redis.calls == [("set", cache.generation_key)]
        assert await cache.get_cached_metric("potential", state="A") is None
        for key, value in before.items():
            if key != cache.generation_key:
                assert cache.redis.values[key] == value
        assert cache.stats["evictions"] == 0
        assert cache.stats["invalidations"] == 1
    asyncio.run(run())


def test_repeated_invalidations_do_constant_work_with_unrelated_keys():
    async def run():
        cache = manager()
        cache.redis.values.update({f"node:pattern:{i}": b"keep" for i in range(10000)})
        for index in range(100):
            assert await cache.invalidate_pattern_metrics(str(index)) == 1
        assert cache.redis.calls == [("set", cache.generation_key)] * 100
        assert len(cache.redis.values) == 10001
    asyncio.run(run())


def test_shared_managers_observe_invalidation_and_concurrent_initialization():
    async def run():
        backend = FakeRedis()
        first, second = manager(backend), manager(backend)
        generations = await asyncio.gather(first.get_cache_generation(), second.get_cache_generation())
        assert generations[0] == generations[1]
        assert await first.cache_metric("potential", 0.25, state="A")
        assert await second.get_cached_metric("potential", state="A") == 0.25
        assert await second.invalidate_pattern_metrics("B") == 1
        assert await first.get_cached_metric("potential", state="A") is None
    asyncio.run(run())


def test_missing_generation_never_resurrects_old_values():
    async def run():
        cache = manager()
        assert await cache.cache_metric("potential", 0.25, state="A")
        old_generation = await cache.get_cache_generation()
        del cache.redis.values[cache.generation_key]
        assert await cache.get_cached_metric("potential", state="A") is None
        assert await cache.get_cache_generation() != old_generation
    asyncio.run(run())


@pytest.mark.parametrize("method,metric,args", [
    ("normalized_entropy_cached", "normalized_entropy", (["A"], 2)),
    ("global_normalized_entropy_cached", "global_normalized_entropy", (["A"], {"A": 0.5}, 2)),
    ("conditional_probability_cached", "conditionalProbability", (["A"], {"A": 0.5})),
])
def test_calculation_spanning_invalidation_cannot_fill_new_generation(monkeypatch, method, metric, args):
    async def run():
        import kato.informatics.metrics as metrics

        calculations = []
        monkeypatch.setattr(metrics, metric, lambda *values: calculations.append(values) or 0.25)
        cache = manager()
        calculator = CachedMetricsCalculator(cache)
        old_generation = await cache.get_cache_generation()
        cache.redis.before_setex = cache.invalidate_all_metrics
        calculate = getattr(calculator, method)
        assert await calculate(*args) == 0.25
        assert await cache.get_cache_generation() != old_generation
        assert next(iter(cache.redis.ttls)).endswith(old_generation)
        assert await calculate(*args) == 0.25  # Old calculation must be a cache miss.
        assert len(calculations) == 2
        assert await calculate(*args) == 0.25  # New generation now contains a hit.
        assert len(calculations) == 2
    asyncio.run(run())


def test_redis_failure_bypasses_cache_without_falling_back_to_old_keys(monkeypatch):
    async def run():
        import kato.informatics.metrics as metrics

        monkeypatch.setattr(metrics, "conditionalProbability", lambda *args: 0.75)
        cache = manager()
        cache.redis.fail_get = True
        assert await cache.get_cached_metric("potential", state="A") is None
        assert not await cache.cache_metric("potential", 0.25, state="A")
        assert await CachedMetricsCalculator(cache).conditional_probability_cached(["A"], {"A": 0.5}) == 0.75
        assert not any(command == "setex" for command, _ in cache.redis.calls)
        cache.redis.fail_set = True
        assert await cache.invalidate_pattern_metrics("A") == 0
        assert cache.stats["invalidations"] == 0
    asyncio.run(run())


def test_disabled_cache_is_a_noop():
    async def run():
        cache = MetricsCacheManager()
        assert await cache.get_cache_generation() is None
        assert await cache.get_cached_metric("potential") is None
        assert not await cache.cache_metric("potential", 0.25)
        assert await cache.invalidate_pattern_metrics("A") == 0
        assert await cache.invalidate_all_metrics() == 0
    asyncio.run(run())
