"""Tests for token redaction in logs, errors, and client helpers."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote

import pytest

from birdweather_mcp.client import _redact, redact_secrets
from birdweather_mcp.server import (
    TokenRedactFilter,
    _err,
    install_token_redact_filter,
)


def test_redact_replaces_raw_and_url_encoded_token():
    token = "tok/with spaces+plus"
    message = f"GET https://example.local/api/{token} and encoded={quote(token)}"
    out = _redact(message, token)
    assert token not in out
    assert quote(token) not in out
    assert quote(token, safe="") not in out
    assert "<token>" in out


def test_redact_noop_without_token():
    assert _redact("hello", None) == "hello"
    assert _redact("hello", "") == "hello"


def test_redact_secrets_covers_station_and_mcp_tokens(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("BIRDWEATHER_STATION_TOKEN", "station-secret-xyz")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "mcp-secret-abc")
    msg = "station-secret-xyz and mcp-secret-abc leaked"
    out = redact_secrets(msg)
    assert "station-secret-xyz" not in out
    assert "mcp-secret-abc" not in out
    assert out.count("<token>") == 2


def test_token_redact_filter_redacts_log_record(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIRDWEATHER_STATION_TOKEN", "filter-station-tok")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "filter-mcp-tok")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="url=/stations/%s/stats auth=%s",
        args=("filter-station-tok", "filter-mcp-tok"),
        exc_info=None,
    )
    assert TokenRedactFilter().filter(record) is True
    assert "filter-station-tok" not in record.getMessage()
    assert "filter-mcp-tok" not in record.getMessage()
    assert "<token>" in record.getMessage()


def test_install_token_redact_filter_on_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIRDWEATHER_STATION_TOKEN", "root-tok-123")
    logging.basicConfig(level=logging.INFO, force=True)
    install_token_redact_filter()
    root = logging.getLogger()
    assert any(isinstance(f, TokenRedactFilter) for f in root.filters)


def test_err_redacts_unexpected_exception_and_does_not_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setenv("BIRDWEATHER_STATION_TOKEN", "err-station-tok")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "err-mcp-tok")
    with caplog.at_level(logging.ERROR, logger="birdweather_mcp"):
        payload = json.loads(
            _err(
                RuntimeError(
                    "failed GET https://app.example/stations/err-station-tok/stats "
                    "auth=err-mcp-tok"
                )
            )
        )
    assert "err-station-tok" not in payload["error"]
    assert "err-mcp-tok" not in payload["error"]
    assert "<token>" in payload["error"]
    assert "err-station-tok" not in caplog.text
    assert "err-mcp-tok" not in caplog.text
    # Must not use logger.exception (no traceback dump of the URL).
    assert "Traceback" not in caplog.text


def test_err_birdweather_error_passthrough_redacted(
    monkeypatch: pytest.MonkeyPatch,
):
    from birdweather_mcp.client import BirdWeatherError

    monkeypatch.setenv("BIRDWEATHER_STATION_TOKEN", "bw-tok")
    payload = json.loads(_err(BirdWeatherError("saw bw-tok in message")))
    assert "bw-tok" not in payload["error"]
    assert "<token>" in payload["error"]
