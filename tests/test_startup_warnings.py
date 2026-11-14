"""Tests for insecure HTTP default warnings at startup."""

from __future__ import annotations

import logging

import pytest

from birdweather_mcp.server import is_loopback_host, warn_insecure_http_defaults


def test_is_loopback_host():
    assert is_loopback_host("127.0.0.1") is True
    assert is_loopback_host("localhost") is True
    assert is_loopback_host("::1") is True
    assert is_loopback_host("[::1]") is True
    assert is_loopback_host("0.0.0.0") is False
    assert is_loopback_host("192.168.1.10") is False
    assert is_loopback_host("nas.example.local") is False


def test_warns_non_loopback_without_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    with caplog.at_level(logging.WARNING, logger="birdweather_mcp"):
        warn_insecure_http_defaults(host="0.0.0.0", transport="streamable-http")
    assert any("MCP_AUTH_TOKEN" in r.message for r in caplog.records)
    assert any("non-loopback" in r.message for r in caplog.records)


def test_no_warn_loopback_without_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    with caplog.at_level(logging.WARNING, logger="birdweather_mcp"):
        warn_insecure_http_defaults(host="127.0.0.1", transport="streamable-http")
    assert not any("SECURITY" in r.message for r in caplog.records)


def test_warns_allowed_hosts_star_without_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*")
    with caplog.at_level(logging.WARNING, logger="birdweather_mcp"):
        # Loopback bind alone would not warn; * hosts still should.
        warn_insecure_http_defaults(host="127.0.0.1", transport="streamable-http")
    assert any("MCP_ALLOWED_HOSTS=*" in r.message for r in caplog.records)


def test_no_warn_when_token_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "sekrit")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*")
    with caplog.at_level(logging.WARNING, logger="birdweather_mcp"):
        warn_insecure_http_defaults(host="0.0.0.0", transport="streamable-http")
    assert not any("SECURITY" in r.message for r in caplog.records)


def test_stdio_skips_warnings(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*")
    with caplog.at_level(logging.WARNING, logger="birdweather_mcp"):
        warn_insecure_http_defaults(host="0.0.0.0", transport="stdio")
    assert not any("SECURITY" in r.message for r in caplog.records)
