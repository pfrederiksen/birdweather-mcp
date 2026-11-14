"""Server tool smoke tests (mocked client / network)."""

from __future__ import annotations

import json

import httpx
import respx

from birdweather_mcp.client import GRAPHQL_URL
from birdweather_mcp.server import (
    get_station,
    search_species,
    species_info,
    top_species,
)


@respx.mock
def test_get_station_tool_json():
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "station": {
                        "id": "12345",
                        "name": "example",
                        "timezone": "America/Los_Angeles",
                    }
                }
            },
        )
    )
    raw = get_station("12345")
    data = json.loads(raw)
    assert data["station"]["id"] == "12345"
    assert "error" not in data


@respx.mock
def test_tool_error_json():
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(200, json={"data": {"station": None}})
    )
    raw = get_station("0")
    data = json.loads(raw)
    assert "error" in data
    assert "not found" in data["error"].lower()


@respx.mock
def test_species_info_tool():
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "species": {
                        "id": "75",
                        "commonName": "Common Raven",
                        "scientificName": "Corvus corax",
                    }
                }
            },
        )
    )
    raw = species_info(scientific_name="Corvus corax")
    data = json.loads(raw)
    assert data["species"]["commonName"] == "Common Raven"


@respx.mock
def test_search_species_tool():
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "searchSpecies": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "75",
                                "commonName": "Common Raven",
                                "scientificName": "Corvus corax",
                            }
                        ],
                    }
                }
            },
        )
    )
    data = json.loads(search_species("raven", limit=5))
    assert data["species"][0]["id"] == "75"


def test_mcp_registers_expected_tools():
    from birdweather_mcp.server import mcp

    tools = mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    expected = {
        "get_station",
        "station_counts",
        "get_weather",
        "recent_detections",
        "top_species",
        "species_list",
        "daily_counts",
        "species_info",
        "search_species",
        "search_stations",
    }
    assert expected.issubset(names)


@respx.mock
def test_top_species_tool_uses_period():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        calls.append(body)
        if "topSpecies" not in body["query"]:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "station": {"timezone": "America/Los_Angeles"}
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "station": {
                        "id": "12345",
                        "name": "example",
                        "timezone": "America/Los_Angeles",
                        "topSpecies": [],
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    data = json.loads(top_species("12345", days=7, limit=3))
    assert data["period"]["timezone"] == "America/Los_Angeles"
    assert "error" not in data
