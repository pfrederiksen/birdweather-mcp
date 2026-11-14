"""Reject unknown tools/call argument keys (is_error, not protocol error)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from mcp import Client

from birdweather_mcp.server import (
    _advertise_no_additional_properties,
    activity_by_hour,
    first_of_year,
    mcp,
    top_species,
)


def _error_text(result) -> str:
    assert result.is_error is True
    assert result.content
    return result.content[0].text


@pytest.mark.asyncio
async def test_top_species_rejects_period_argument():
    result = await mcp.call_tool(
        "top_species",
        {"station_id": "12345", "period": "day", "limit": 3},
    )
    text = _error_text(result)
    payload = json.loads(text)
    err = payload["error"]
    assert "period" in err
    assert "days" in err
    assert "from_date" in err and "to_date" in err
    assert "time window" in err.lower() or "from_date/to_date" in err


@pytest.mark.asyncio
async def test_top_species_valid_args_still_work():
    fake = {
        "station": {"id": "12345", "name": "Example Station", "timezone": "UTC"},
        "period": {"from": "2026-11-08", "to": "2026-11-14", "timezone": "UTC"},
        "species": [],
        "source": "graphql",
    }
    with patch("birdweather_mcp.server._client") as client_factory:
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = None
        client.top_species.return_value = fake
        client_factory.return_value = client
        result = await mcp.call_tool(
            "top_species",
            {"station_id": "12345", "days": 7, "limit": 3},
        )
    assert result.is_error is False
    data = json.loads(result.content[0].text)
    assert data["station"]["id"] == "12345"
    client.top_species.assert_called_once()


@pytest.mark.asyncio
async def test_activity_by_hour_rejects_hours_argument():
    result = await mcp.call_tool(
        "activity_by_hour",
        {"station_id": "12345", "hours": 24},
    )
    text = _error_text(result)
    payload = json.loads(text)
    err = payload["error"]
    assert "hours" in err
    assert "activity_by_hour" in err
    assert "days" in err


@pytest.mark.asyncio
async def test_first_of_year_from_date_suggests_since_until():
    result = await mcp.call_tool(
        "first_of_year",
        {"station_id": "12345", "from_date": "2026-01-01"},
    )
    text = _error_text(result)
    payload = json.loads(text)
    err = payload["error"]
    assert "from_date" in err
    assert "since" in err
    # Suggestion path (alias), not the days/from_date/to_date window hint.
    assert "Did you mean 'since'" in err


@pytest.mark.asyncio
async def test_unknown_args_over_in_memory_client_protocol_path():
    """Client(mcp) drives the server call_tool path (same handler as stdio/HTTP)."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "top_species",
            {"station_id": "12345", "period": "day", "limit": 3},
        )
    text = _error_text(result)
    payload = json.loads(text)
    assert "period" in payload["error"]
    assert "days" in payload["error"]


@pytest.mark.asyncio
async def test_tool_schemas_advertise_additional_properties_false():
    tools = await mcp.list_tools()
    by_name = {t.name: t for t in tools}
    for name in ("top_species", "activity_by_hour", "first_of_year", "get_station"):
        schema = by_name[name].input_schema
        assert schema.get("additionalProperties") is False


def test_advertise_helper_is_idempotent():
    _advertise_no_additional_properties(mcp)
    tool = mcp._tool_manager.get_tool("top_species")
    assert tool is not None
    assert tool.parameters.get("additionalProperties") is False


def test_direct_tool_fns_unaffected_by_unknown_kwargs_at_python_level():
    """Python call sites still use real kwargs; rejection is MCP call_tool only."""
    # Sanity: the decorated functions exist and reject unexpected kwargs themselves.
    with pytest.raises(TypeError):
        top_species(station_id="12345", period="day")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        activity_by_hour(station_id="12345", hours=24)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        first_of_year(station_id="12345", from_date="2026-01-01")  # type: ignore[call-arg]
