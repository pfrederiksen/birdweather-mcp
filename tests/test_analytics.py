"""Unit tests for trend / arrivals / compare / hourly tools."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from birdweather_mcp.client import (
    GRAPHQL_URL,
    BirdWeatherClient,
    BirdWeatherError,
    aggregate_hourly_counts,
    enrich_detection_media,
    rollup_weekly_counts,
)


def test_enrich_detection_media_soundscape_and_spectrogram():
    det = {
        "id": "1",
        "soundscape": {
            "url": "https://media.birdweather.com/soundscapes/example.flac",
            "spectrogramUrl": "https://media.birdweather.com/spectrograms/example.png",
        },
        "species": {
            "id": "134",
            "commonName": "House Finch",
            "imageUrl": "https://media.birdweather.com/species/134/img.jpg",
            "thumbnailUrl": "https://media.birdweather.com/species/134/thumb.jpg",
        },
    }
    out = enrich_detection_media(det)
    assert out["audio_url"].endswith(".flac")
    assert out["spectrogram_url"].endswith(".png")
    assert out["species_image_url"].endswith("img.jpg")
    assert out["species_thumbnail_url"].endswith("thumb.jpg")


def test_aggregate_hourly_counts_local_tz():
    period = {
        "from": "2026-11-14",
        "to": "2026-11-14",
        "timezone": "America/Los_Angeles",
    }
    detections = [
        {"timestamp": "2026-11-14T08:15:00-08:00"},
        {"timestamp": "2026-11-14T08:45:00-08:00"},
        {"timestamp": "2026-11-14T16:00:00Z"},  # 08:00 local
        {"timestamp": "2026-11-15T10:00:00-08:00"},  # outside range
    ]
    hours = aggregate_hourly_counts(detections, period=period)
    assert hours[8]["count"] == 3
    assert sum(h["count"] for h in hours) == 3


def test_rollup_weekly_counts():
    daily = [
        {"date": "2026-11-09", "total": 1},
        {"date": "2026-11-10", "total": 2},
        {"date": "2026-11-16", "total": 4},
    ]
    weeks = rollup_weekly_counts(daily)
    assert len(weeks) == 2
    assert weeks[0]["total"] == 3
    assert weeks[1]["total"] == 4


@respx.mock
def test_species_trend_day(client: BirdWeatherClient):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        q = body["query"]
        if "searchSpecies" in q:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "searchSpecies": {
                            "nodes": [
                                {
                                    "id": "134",
                                    "commonName": "House Finch",
                                    "scientificName": "Haemorhous mexicanus",
                                }
                            ],
                            "pageInfo": {"hasNextPage": False},
                        }
                    }
                },
            )
        if "species(" in q and "detections" not in q:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "species": {
                            "id": "134",
                            "commonName": "House Finch",
                            "scientificName": "Haemorhous mexicanus",
                        }
                    }
                },
            )
        if "timezone" in q and "detections" not in q:
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
                        "detections": {
                            "pageInfo": {"hasNextPage": False},
                            "nodes": [
                                {
                                    "timestamp": "2026-11-13T10:00:00-08:00",
                                    "speciesId": "134",
                                    "species": {
                                        "id": "134",
                                        "commonName": "House Finch",
                                    },
                                },
                                {
                                    "timestamp": "2026-11-14T10:00:00-08:00",
                                    "speciesId": "134",
                                    "species": {
                                        "id": "134",
                                        "commonName": "House Finch",
                                    },
                                },
                            ],
                        },
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    out = client.species_trend(
        12345,
        "House Finch",
        from_date="2026-11-13",
        to_date="2026-11-14",
        granularity="day",
    )
    assert out["granularity"] == "day"
    assert out["series"][0]["date"] == "2026-11-13"
    assert out["series"][0]["total"] == 1
    assert out["series"][1]["total"] == 1


@respx.mock
def test_compare_stations(client: BirdWeatherClient):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        sid = str(body.get("variables", {}).get("id"))
        if "topSpecies" not in body["query"]:
            return httpx.Response(
                200,
                json={"data": {"station": {"timezone": "America/Los_Angeles"}}},
            )
        if sid == "12345":
            species = [
                {
                    "speciesId": "134",
                    "count": 10,
                    "species": {
                        "id": "134",
                        "commonName": "House Finch",
                        "scientificName": "Haemorhous mexicanus",
                    },
                },
                {
                    "speciesId": "75",
                    "count": 2,
                    "species": {
                        "id": "75",
                        "commonName": "Common Raven",
                        "scientificName": "Corvus corax",
                    },
                },
            ]
        else:
            species = [
                {
                    "speciesId": "134",
                    "count": 5,
                    "species": {
                        "id": "134",
                        "commonName": "House Finch",
                        "scientificName": "Haemorhous mexicanus",
                    },
                },
                {
                    "speciesId": "414",
                    "count": 3,
                    "species": {
                        "id": "414",
                        "commonName": "Anna's Hummingbird",
                        "scientificName": "Calypte anna",
                    },
                },
            ]
        return httpx.Response(
            200,
            json={
                "data": {
                    "station": {
                        "id": sid,
                        "name": "Example Station" if sid == "12345" else "Nearby Example Pi",
                        "timezone": "America/Los_Angeles",
                        "topSpecies": species,
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    out = client.compare_stations(12345, 67890, days=7)
    assert out["summary"]["shared"] == 1
    assert out["summary"]["only_a"] == 1
    assert out["summary"]["only_b"] == 1
    assert out["overlap"][0]["speciesId"] == "134"


@respx.mock
def test_activity_by_hour(client: BirdWeatherClient):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if "detections" not in body["query"]:
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
                        "detections": {
                            "pageInfo": {"hasNextPage": False},
                            "nodes": [
                                {"timestamp": "2026-11-14T07:00:00-08:00"},
                                {"timestamp": "2026-11-14T07:30:00-08:00"},
                                {"timestamp": "2026-11-14T18:00:00-08:00"},
                            ],
                        },
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    out = client.activity_by_hour(
        12345, from_date="2026-11-14", to_date="2026-11-14"
    )
    assert out["hours"][7]["count"] == 2
    assert out["hours"][18]["count"] == 1
    assert out["total"] == 3


@respx.mock
def test_first_of_year(client: BirdWeatherClient):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        q = body["query"]
        vars_ = body.get("variables") or {}
        if "timezone" in q and "detections" not in q and "topSpecies" not in q:
            return httpx.Response(
                200,
                json={"data": {"station": {"timezone": "America/Los_Angeles"}}},
            )
        if "topSpecies" in q:
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
                                    "count": 3,
                                    "species": {
                                        "id": "134",
                                        "commonName": "House Finch",
                                        "scientificName": "Haemorhous mexicanus",
                                    },
                                },
                                {
                                    "speciesId": "75",
                                    "count": 1,
                                    "species": {
                                        "id": "75",
                                        "commonName": "Common Raven",
                                        "scientificName": "Corvus corax",
                                    },
                                },
                            ],
                        }
                    }
                },
            )
        # earliest detection per species
        sid = str(vars_.get("speciesId"))
        if sid == "134":
            # first seen earlier in the year — not a new arrival
            node = {
                "id": "1",
                "timestamp": "2026-03-01T08:00:00-08:00",
                "speciesId": "134",
                "species": {
                    "id": "134",
                    "commonName": "House Finch",
                    "scientificName": "Haemorhous mexicanus",
                },
                "soundscape": {"url": "https://media.birdweather.com/soundscapes/a.flac"},
            }
        else:
            node = {
                "id": "2",
                "timestamp": "2026-11-10T09:00:00-08:00",
                "speciesId": "75",
                "species": {
                    "id": "75",
                    "commonName": "Common Raven",
                    "scientificName": "Corvus corax",
                },
                "soundscape": {
                    "url": "https://media.birdweather.com/soundscapes/b.flac",
                    "spectrogramUrl": "https://media.birdweather.com/spectrograms/b.png",
                },
            }
        return httpx.Response(
            200,
            json={
                "data": {
                    "station": {
                        "id": "12345",
                        "detections": {
                            "nodes": [node],
                            "pageInfo": {"hasNextPage": False},
                        },
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    out = client.first_of_year(
        12345,
        since="2026-01-01",
        until="2026-11-14",
        timezone="America/Los_Angeles",
    )
    assert len(out["species"]) == 1
    assert out["species"][0]["speciesId"] == "75"
    assert out["species"][0]["audio_url"].endswith(".flac")
    assert out["species"][0]["spectrogram_url"].endswith(".png")


def test_species_trend_bad_granularity(client: BirdWeatherClient):
    with pytest.raises(BirdWeatherError, match="granularity"):
        client.species_trend(12345, "134", days=3, granularity="month")


def test_server_registers_new_tools():
    from birdweather_mcp.server import mcp

    names = {t.name for t in mcp._tool_manager.list_tools()}
    for name in (
        "species_trend",
        "first_of_year",
        "new_arrivals",
        "compare_stations",
        "activity_by_hour",
    ):
        assert name in names
