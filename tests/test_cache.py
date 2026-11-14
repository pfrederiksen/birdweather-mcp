"""Unit tests for TTL cache and retry behaviour."""

from __future__ import annotations

import json
import time

import httpx
import pytest
import respx

from birdweather_mcp.cache import TTLCache, cache_enabled_from_env, make_cache_key
from birdweather_mcp.client import GRAPHQL_URL, BirdWeatherClient, BirdWeatherError


def test_ttl_cache_get_set_expire():
    cache = TTLCache(ttl_seconds=0.05, max_entries=8)
    cache.set("a", {"ok": True})
    assert cache.get("a") == {"ok": True}
    assert cache.hits == 1
    time.sleep(0.06)
    assert cache.get("a") is None
    assert cache.misses >= 1


def test_ttl_cache_lru_eviction():
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_ttl_cache_disabled():
    cache = TTLCache(ttl_seconds=0, max_entries=10)
    assert not cache.enabled
    cache.set("a", 1)
    assert cache.get("a") is None


def test_make_cache_key_stable():
    assert make_cache_key("g", {"b": 1, "a": 2}) == make_cache_key(
        "g", {"a": 2, "b": 1}
    )


def test_cache_enabled_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIRDWEATHER_CACHE_ENABLED", "false")
    assert cache_enabled_from_env() is False
    monkeypatch.setenv("BIRDWEATHER_CACHE_ENABLED", "true")
    monkeypatch.setenv("BIRDWEATHER_CACHE_TTL", "0")
    # explicit true wins over ttl=0? Spec: either disables. ENABLED=true + TTL=0 →
    # enabled_from_env returns True for flag, but from_env uses ttl. Keep flag path.
    assert cache_enabled_from_env() is True
    monkeypatch.delenv("BIRDWEATHER_CACHE_ENABLED")
    monkeypatch.setenv("BIRDWEATHER_CACHE_TTL", "0")
    assert cache_enabled_from_env() is False


@respx.mock
def test_graphql_uses_cache():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"data": {"station": {"id": "12345", "name": "Example Station"}}},
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    cache = TTLCache(ttl_seconds=60, max_entries=32)
    client = BirdWeatherClient(max_retries=1, cache=cache, timeout=5.0)
    q = 'query { station(id: "12345") { id name } }'
    a = client.graphql(q)
    b = client.graphql(q)
    assert a == b
    assert calls["n"] == 1
    assert cache.hits == 1
    client.close()


@respx.mock
def test_graphql_retries_429_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "birdweather_mcp.client._backoff_seconds", lambda attempt, **kw: 0
    )
    responses = [
        httpx.Response(429, json={"errors": [{"message": "slow down"}]}),
        httpx.Response(
            200,
            json={"data": {"station": {"id": "12345"}}},
        ),
    ]
    respx.post(GRAPHQL_URL).mock(side_effect=responses)
    client = BirdWeatherClient(max_retries=3, use_cache=False, timeout=5.0)
    out = client.graphql('query { station(id: "12345") { id } }')
    assert out["station"]["id"] == "12345"
    client.close()


@respx.mock
def test_graphql_does_not_retry_400(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "birdweather_mcp.client._backoff_seconds", lambda attempt, **kw: 0
    )
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(400, text="bad"))
    client = BirdWeatherClient(max_retries=3, use_cache=False, timeout=5.0)
    with pytest.raises(BirdWeatherError, match="failed"):
        client.graphql("query { nope }")
    client.close()


@respx.mock
def test_graphql_retries_5xx_exhausted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "birdweather_mcp.client._backoff_seconds", lambda attempt, **kw: 0
    )
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(503, text="down"))
    client = BirdWeatherClient(max_retries=2, use_cache=False, timeout=5.0)
    with pytest.raises(BirdWeatherError, match="after retries"):
        client.graphql("query { station(id: \"1\") { id } }")
    client.close()


@pytest.mark.asyncio
async def test_health_route():
    from birdweather_mcp.server import health_check

    class _Req:
        pass

    resp = await health_check(_Req())  # type: ignore[arg-type]
    body = json.loads(resp.body.decode())
    assert body["status"] == "ok"
    assert "version" in body
