"""Тесты TTL-кеша."""
from __future__ import annotations

from cache.ttl_cache import TTLCache


def test_ttl_expiry():
    now = [100.0]
    cache = TTLCache(ttl_seconds=10, clock=lambda: now[0])

    cache.set("k", "v")
    assert cache.get("k") == "v"

    now[0] = 111.0
    assert cache.get("k") is None


def test_key_depends_on_all_parameters():
    cache = TTLCache()
    base = {
        "text": "текст",
        "model": "m",
        "temperature": 0.2,
        "system_prompt": "system",
        "scenario": "summarize",
    }
    key = cache.make_key(**base)

    assert key == cache.make_key(**base)
    assert key != cache.make_key(**{**base, "text": "другой"})
    assert key != cache.make_key(**{**base, "model": "m2"})
    assert key != cache.make_key(**{**base, "temperature": 0.9})
    assert key != cache.make_key(**{**base, "system_prompt": "system2"})
    assert key != cache.make_key(**{**base, "scenario": "other"})


def test_max_entries_eviction():
    cache = TTLCache(ttl_seconds=100, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.stats()["size"] == 2


def test_stats_count_hits_and_misses():
    cache = TTLCache(ttl_seconds=100)
    cache.set("k", "v")

    cache.get("k")
    cache.get("missing")

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
