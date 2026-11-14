"""Server tool smoke tests (mocked client / network)."""

from __future__ import annotations

import json

import httpx
import respx

from birdweather_mcp.client import GRAPHQL_URL
from birdweather_mcp.server import (
    get_station,
    parse_allowed_hosts,
    search_species,
    species_info,
    top_species,
    transport_security_from_env,
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


def test_parse_allowed_hosts():
    assert parse_allowed_hosts(None) is None
    assert parse_allowed_hosts("") is None
    assert parse_allowed_hosts("  ") is None
    assert parse_allowed_hosts("*") == []
    assert parse_allowed_hosts("nas.example.local:*") == ["nas.example.local:*"]
    assert parse_allowed_hosts("a.example, b.example:*") == [
        "a.example",
        "b.example:*",
    ]


def test_transport_security_from_env_star_disables_protection():
    settings = transport_security_from_env("*")
    assert settings is not None
    assert settings.enable_dns_rebinding_protection is False


def test_transport_security_from_env_merges_loopback():
    settings = transport_security_from_env("mcp.home.example:*")
    assert settings is not None
    assert settings.enable_dns_rebinding_protection is True
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "mcp.home.example:*" in settings.allowed_hosts
    assert "http://mcp.home.example:*" in settings.allowed_origins
    assert "https://mcp.home.example:*" in settings.allowed_origins


def test_transport_security_from_env_unset():
    assert transport_security_from_env("") is None
    assert transport_security_from_env(None) is None


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
