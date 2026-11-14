"""Tests for MCP prompts and resources."""

from __future__ import annotations

import json

import httpx
import respx

from birdweather_mcp.client import GRAPHQL_URL
from birdweather_mcp.server import (
    daily_station_summary,
    mcp,
    species_deep_dive,
    station_info_resource,
    station_species_list_resource,
    weekly_report,
)


def test_prompts_registered():
    names = {p.name for p in mcp._prompt_manager.list_prompts()}
    assert {
        "daily_station_summary",
        "weekly_report",
        "species_deep_dive",
    }.issubset(names)


def test_prompt_text_uses_placeholders():
    text = daily_station_summary("12345")
    assert "12345" in text
    assert "top_species" in text
    assert "House Finch" in species_deep_dive("12345", "House Finch")
    assert "activity_by_hour" in weekly_report("12345")


def test_resources_registered():
    # Templates are registered for parameterized URIs.
    templates = mcp._resource_manager.list_templates()
    uris = {t.uri_template for t in templates}
    assert "birdweather://station/{station_id}" in uris
    assert "birdweather://station/{station_id}/species" in uris


@respx.mock
def test_station_info_resource():
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "station": {
                        "id": "12345",
                        "name": "Example Station",
                        "timezone": "America/Los_Angeles",
                    }
                }
            },
        )
    )
    data = json.loads(station_info_resource("12345"))
    assert data["station"]["name"] == "Example Station"


@respx.mock
def test_station_species_list_resource():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if "topSpecies" not in body["query"]:
            return httpx.Response(
                200,
                json={"data": {"station": {"timezone": "America/Los_Angeles"}}},
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "station": {
                        "id": "12345",
                        "name": "Example Station",
                        "timezone": "America/Los_Angeles",
                        "topSpecies": [
                            {
                                "speciesId": "134",
                                "count": 10,
                                "species": {
                                    "id": "134",
                                    "commonName": "House Finch",
                                },
                            }
                        ],
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    data = json.loads(station_species_list_resource("12345"))
    assert data["species"][0]["speciesId"] == "134"
