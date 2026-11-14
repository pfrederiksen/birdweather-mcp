"""Input validation tests for station ids, periods, queries, and enums."""

from __future__ import annotations

import json

import pytest

from birdweather_mcp.client import (
    BirdWeatherClient,
    BirdWeatherError,
    build_period,
    validate_species_query,
    validate_station_id,
)
from birdweather_mcp.server import daily_station_summary, get_station


def test_validate_station_id_accepts_safe_ids():
    assert validate_station_id("12345") == "12345"
    assert validate_station_id("abc_DEF-9") == "abc_DEF-9"


def test_validate_station_id_rejects_bad_values():
    with pytest.raises(BirdWeatherError, match="empty"):
        validate_station_id("  ")
    with pytest.raises(BirdWeatherError, match="at most 32"):
        validate_station_id("x" * 33)
    with pytest.raises(BirdWeatherError, match=r"\^\[A-Za-z0-9_-\]\+\$"):
        validate_station_id("../etc/passwd")
    with pytest.raises(BirdWeatherError, match=r"\^\[A-Za-z0-9_-\]\+\$"):
        validate_station_id("12 34")


def test_validate_species_query_length():
    assert validate_species_query("raven") == "raven"
    with pytest.raises(BirdWeatherError, match="empty"):
        validate_species_query("   ")
    with pytest.raises(BirdWeatherError, match="at most 100"):
        validate_species_query("a" * 101)


def test_build_period_caps_days():
    with pytest.raises(BirdWeatherError, match="days must be <= 366"):
        build_period(days=367, timezone="UTC")
    period = build_period(days=366, timezone="UTC")
    assert period["from"] <= period["to"]


def test_build_period_rejects_inverted_and_long_ranges():
    with pytest.raises(BirdWeatherError, match="on or after"):
        build_period(from_date="2026-12-01", to_date="2026-01-01", timezone="UTC")
    with pytest.raises(BirdWeatherError, match="must not exceed 366"):
        build_period(
            from_date="2025-01-01",
            to_date="2026-01-02",
            timezone="UTC",
        )
    # Exactly 366 inclusive days is allowed.
    period = build_period(
        from_date="2025-01-01",
        to_date="2025-12-31",
        timezone="UTC",
    )
    assert period["from"] == "2025-01-01"
    assert period["to"] == "2025-12-31"


def test_rest_path_must_be_allowlisted():
    client = BirdWeatherClient(station_token="tok", max_retries=1)
    with pytest.raises(BirdWeatherError, match="Invalid REST path"):
        client.rest_get("../admin")
    with pytest.raises(BirdWeatherError, match="period must be one of"):
        client.rest_get("stats", {"period": "forever"})
    client.close()


def test_species_trend_rejects_bad_granularity():
    client = BirdWeatherClient(max_retries=1)
    with pytest.raises(BirdWeatherError, match="granularity"):
        client.species_trend("12345", "134", granularity="hour")
    client.close()


def test_limit_clamped_in_search_species(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_graphql(self, query, variables=None):
        captured["variables"] = variables
        return {
            "searchSpecies": {
                "nodes": [],
                "totalCount": 0,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

    monkeypatch.setattr(BirdWeatherClient, "graphql", fake_graphql)
    client = BirdWeatherClient(max_retries=1)
    client.search_species("finch", limit=999)
    assert captured["variables"]["first"] == 100
    client.close()


def test_tool_rejects_invalid_station_id():
    data = json.loads(get_station("../bad"))
    assert "error" in data
    assert "station_id" in data["error"].lower() or "must match" in data["error"]


def test_prompt_rejects_invalid_station_id():
    with pytest.raises(BirdWeatherError):
        daily_station_summary("bad id!")


def test_graphql_keeps_values_in_variables(monkeypatch: pytest.MonkeyPatch):
    """Station ids must travel as GraphQL variables, never string-interpolated."""
    seen: list[tuple[str, dict]] = []

    def fake_graphql(self, query, variables=None):
        seen.append((query, variables or {}))
        return {
            "station": {
                "id": "12345",
                "name": "example",
                "timezone": "UTC",
            }
        }

    monkeypatch.setattr(BirdWeatherClient, "graphql", fake_graphql)
    client = BirdWeatherClient(max_retries=1)
    client.get_station("12345")
    query, variables = seen[0]
    assert "12345" not in query
    assert variables["id"] == "12345"
    client.close()
