"""Tests for optional HTTP bearer auth."""

from __future__ import annotations

import json

import pytest

from birdweather_mcp.auth import (
    BearerAuthMiddleware,
    extract_bearer_token,
    tokens_match,
    wrap_app_with_optional_auth,
)


def test_extract_bearer_token():
    assert extract_bearer_token("Bearer secret") == "secret"
    assert extract_bearer_token("bearer secret") == "secret"
    assert extract_bearer_token("Basic x") is None
    assert extract_bearer_token(None) is None
    assert extract_bearer_token("") is None


def test_tokens_match_uses_constant_time_equality():
    assert tokens_match("secret", "secret") is True
    assert tokens_match("wrong", "secret") is False
    assert tokens_match("sekrit!", "secret") is False  # different lengths


@pytest.mark.asyncio
async def test_middleware_allows_health_without_token():
    called = {"ok": False}

    async def app(scope, receive, send):
        called["ok"] = True
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    mw = BearerAuthMiddleware(app, expected_token="secret")
    events: list[dict] = []

    async def send(message):
        events.append(message)

    await mw(
        {
            "type": "http",
            "path": "/health",
            "headers": [],
        },
        None,  # type: ignore[arg-type]
        send,
    )
    assert called["ok"] is True
    assert events[0]["status"] == 200


@pytest.mark.asyncio
async def test_middleware_health_is_exact_path_only():
    """Traversal-style paths must not inherit /health public access."""

    async def app(scope, receive, send):
        raise AssertionError("should not reach app")

    mw = BearerAuthMiddleware(app, expected_token="secret")
    events: list[dict] = []

    async def send(message):
        events.append(message)

    await mw(
        {"type": "http", "path": "/health/../mcp", "headers": []},
        None,  # type: ignore[arg-type]
        send,
    )
    assert events[0]["status"] == 401


@pytest.mark.asyncio
async def test_middleware_rejects_mcp_without_bearer():
    async def app(scope, receive, send):
        raise AssertionError("should not reach app")

    mw = BearerAuthMiddleware(app, expected_token="secret")
    events: list[dict] = []

    async def send(message):
        events.append(message)

    await mw(
        {"type": "http", "path": "/mcp", "headers": []},
        None,  # type: ignore[arg-type]
        send,
    )
    assert events[0]["status"] == 401
    body = events[1]["body"]
    assert json.loads(body.decode())["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_middleware_rejects_wrong_token():
    async def app(scope, receive, send):
        raise AssertionError("should not reach app")

    mw = BearerAuthMiddleware(app, expected_token="secret")
    events: list[dict] = []

    async def send(message):
        events.append(message)

    await mw(
        {
            "type": "http",
            "path": "/mcp",
            "headers": [(b"authorization", b"Bearer wrong-token")],
        },
        None,  # type: ignore[arg-type]
        send,
    )
    assert events[0]["status"] == 401


@pytest.mark.asyncio
async def test_middleware_rejects_wrong_scheme():
    async def app(scope, receive, send):
        raise AssertionError("should not reach app")

    mw = BearerAuthMiddleware(app, expected_token="secret")
    events: list[dict] = []

    async def send(message):
        events.append(message)

    await mw(
        {
            "type": "http",
            "path": "/mcp",
            "headers": [(b"authorization", b"Basic secret")],
        },
        None,  # type: ignore[arg-type]
        send,
    )
    assert events[0]["status"] == 401


@pytest.mark.asyncio
async def test_middleware_accepts_valid_bearer():
    called = {"ok": False}

    async def app(scope, receive, send):
        called["ok"] = True
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    mw = BearerAuthMiddleware(app, expected_token="secret")
    events: list[dict] = []

    async def send(message):
        events.append(message)

    await mw(
        {
            "type": "http",
            "path": "/mcp",
            "headers": [(b"authorization", b"Bearer secret")],
        },
        None,  # type: ignore[arg-type]
        send,
    )
    assert called["ok"] is True
    assert events[0]["status"] == 200


@pytest.mark.asyncio
async def test_middleware_rejects_websocket_when_token_set():
    called = {"ok": False}

    async def app(scope, receive, send):
        called["ok"] = True

    mw = BearerAuthMiddleware(app, expected_token="secret")
    events: list[dict] = []

    async def send(message):
        events.append(message)

    await mw({"type": "websocket", "path": "/mcp", "headers": []}, None, send)  # type: ignore[arg-type]
    assert called["ok"] is False
    assert events == [{"type": "websocket.close", "code": 1008}]


@pytest.mark.asyncio
async def test_middleware_allows_lifespan_when_token_set():
    called = {"ok": False}

    async def app(scope, receive, send):
        called["ok"] = True

    mw = BearerAuthMiddleware(app, expected_token="secret")
    await mw({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    assert called["ok"] is True


def test_wrap_app_noop_without_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    async def app(scope, receive, send):
        return None

    assert wrap_app_with_optional_auth(app) is app


def test_wrap_app_with_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "sekrit")

    async def app(scope, receive, send):
        return None

    wrapped = wrap_app_with_optional_auth(app)
    assert isinstance(wrapped, BearerAuthMiddleware)
