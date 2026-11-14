"""Unit tests for BirdWeatherClient (mocked network)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from birdweather_mcp.client import (
    GRAPHQL_URL,
    REST_BASE,
    BirdWeatherClient,
    BirdWeatherError,
    aggregate_daily_counts,
    bbox_from_point,
    build_period,
    detection_local_date,
)


def test_build_period_days():
    period = build_period(days=3, timezone="America/Los_Angeles")
    assert period["timezone"] == "America/Los_Angeles"
    assert period["from"] <= period["to"]
    # inclusive window length
    from datetime import date

    start = date.fromisoformat(period["from"])
    end = date.fromisoformat(period["to"])
    assert (end - start).days == 2


def test_build_period_rejects_bad_tz():
    with pytest.raises(BirdWeatherError, match="Unknown timezone"):
        build_period(days=1, timezone="Not/AZone")


def test_build_period_from_to():
    period = build_period(
        from_date="2026-11-01", to_date="2026-11-14", timezone="UTC"
    )
    assert period == {
        "from": "2026-11-01",
        "to": "2026-11-14",
        "timezone": "UTC",
    }


def test_bbox_from_point():
    ne, sw = bbox_from_point(37.77, -122.42, 10)
    assert sw["lat"] < 37.77 < ne["lat"]
    assert sw["lon"] < -122.42 < ne["lon"]


def test_detection_local_date_crosses_utc_midnight():
    # 2026-11-14 01:30 UTC = 2026-11-13 evening in America/Los_Angeles
    assert (
        detection_local_date(
            "2026-11-14T01:30:00+00:00", "America/Los_Angeles"
        ).isoformat()
        == "2026-11-13"
    )
    assert (
        detection_local_date(
            "2026-11-14T16:00:00Z", "America/Los_Angeles"
        ).isoformat()
        == "2026-11-14"
    )


def test_aggregate_daily_counts_honors_timezone_and_range():
    period = {
        "from": "2026-11-13",
        "to": "2026-11-13",
        "timezone": "America/Los_Angeles",
    }
    detections = [
        # UTC morning → still Nov 12 local? No: 08:00 UTC = Nov 13 00:00 PST
        {
            "timestamp": "2026-11-13T08:00:00+00:00",
            "speciesId": "134",
            "species": {
                "id": "134",
                "commonName": "House Finch",
                "scientificName": "Haemorhous mexicanus",
            },
        },
        # Late evening local Nov 13 (= Nov 14 UTC) must count as Nov 13 local
        {
            "timestamp": "2026-11-14T06:00:00+00:00",
            "speciesId": "134",
            "species": {
                "id": "134",
                "commonName": "House Finch",
                "scientificName": "Haemorhous mexicanus",
            },
        },
        # Outside requested local day (Nov 14 local morning)
        {
            "timestamp": "2026-11-14T16:00:00+00:00",
            "speciesId": "75",
            "species": {
                "id": "75",
                "commonName": "Common Raven",
                "scientificName": "Corvus corax",
            },
        },
    ]
    rows = aggregate_daily_counts(detections, period=period)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-11-13"
    assert rows[0]["total"] == 2
    assert rows[0]["counts"][0]["speciesId"] == "134"
    assert rows[0]["counts"][0]["count"] == 2


def test_aggregate_daily_counts_filters_extra_following_day():
    """Simulate GraphQL overshoot: from==to must not keep a following-day row."""
    period = {
        "from": "2026-11-14",
        "to": "2026-11-14",
        "timezone": "America/Los_Angeles",
    }
    detections = [
        {
            "timestamp": "2026-11-14T20:00:00-08:00",
            "speciesId": "1",
            "species": {"id": "1", "commonName": "A", "scientificName": "A a"},
        },
        {
            "timestamp": "2026-11-15T01:00:00-08:00",
            "speciesId": "2",
            "species": {"id": "2", "commonName": "B", "scientificName": "B b"},
        },
    ]
    rows = aggregate_daily_counts(
        detections, period=period, include_species_breakdown=False
    )
    assert [r["date"] for r in rows] == ["2026-11-14"]
    assert rows[0]["total"] == 1
    assert "counts" not in rows[0]


@respx.mock
def test_daily_counts_aggregates_from_detections(client: BirdWeatherClient):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        q = body["query"]
        if "detections" not in q:
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
                        "name": "Example Station",
                        "timezone": "America/Los_Angeles",
                        "detections": {
                            "totalCount": 2,
                            "speciesCount": 1,
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                            "nodes": [
                                {
                                    "id": "1",
                                    "timestamp": "2026-11-14T10:00:00-08:00",
                                    "speciesId": "134",
                                    "species": {
                                        "id": "134",
                                        "commonName": "House Finch",
                                        "scientificName": "Haemorhous mexicanus",
                                    },
                                },
                                {
                                    "id": "2",
                                    "timestamp": "2026-11-14T18:00:00-08:00",
                                    "speciesId": "134",
                                    "species": {
                                        "id": "134",
                                        "commonName": "House Finch",
                                        "scientificName": "Haemorhous mexicanus",
                                    },
                                },
                            ],
                        },
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    out = client.daily_counts(
        12345,
        from_date="2026-11-14",
        to_date="2026-11-14",
        include_species_breakdown=True,
    )
    assert out["period"]["timezone"] == "America/Los_Angeles"
    assert len(out["days"]) == 1
    assert out["days"][0]["date"] == "2026-11-14"
    assert out["days"][0]["total"] == 2


@respx.mock
def test_get_station(client: BirdWeatherClient):
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "station": {
                        "id": "12345",
                        "name": "example",
                        "timezone": "America/Los_Angeles",
                        "coords": {"lat": 37.77, "lon": -122.42},
                    }
                }
            },
        )
    )
    out = client.get_station(12345)
    assert out["station"]["id"] == "12345"
    assert out["source"] == "graphql"


@respx.mock
def test_get_station_not_found(client: BirdWeatherClient):
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(200, json={"data": {"station": None}})
    )
    with pytest.raises(BirdWeatherError, match="not found"):
        client.get_station(999)


@respx.mock
def test_graphql_errors_surface(client: BirdWeatherClient):
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200, json={"errors": [{"message": "boom"}]}
        )
    )
    with pytest.raises(BirdWeatherError, match="boom"):
        client.graphql("query { station(id: \"1\") { id } }")


@respx.mock
def test_recent_detections(client: BirdWeatherClient):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        q = body["query"]
        if "timezone" in q and "detections" not in q:
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
                        "detections": {
                            "totalCount": 1,
                            "speciesCount": 1,
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": "abc",
                            },
                            "nodes": [
                                {
                                    "id": "1",
                                    "timestamp": "2026-11-14T08:00:00-08:00",
                                    "confidence": 0.9,
                                    "species": {
                                        "id": "134",
                                        "commonName": "House Finch",
                                        "scientificName": "Haemorhous mexicanus",
                                    },
                                }
                            ],
                        },
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    out = client.recent_detections(
        12345, days=1, min_confidence=0.7, limit=10
    )
    assert len(out["detections"]) == 1
    assert out["detections"][0]["species"]["commonName"] == "House Finch"
    assert out["source"] == "graphql"


@respx.mock
def test_top_species(client: BirdWeatherClient):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
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
                        "topSpecies": [
                            {
                                "speciesId": "134",
                                "count": 10,
                                "species": {
                                    "id": "134",
                                    "commonName": "House Finch",
                                    "scientificName": "Haemorhous mexicanus",
                                },
                            }
                        ],
                    }
                }
            },
        )

    respx.post(GRAPHQL_URL).mock(side_effect=handler)
    out = client.top_species(12345, days=7, limit=5)
    assert out["species"][0]["count"] == 10


@respx.mock
def test_search_stations_with_distance(client: BirdWeatherClient):
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "stations": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "12345",
                                "name": "example",
                                "coords": {"lat": 37.77, "lon": -122.42},
                            }
                        ],
                    }
                }
            },
        )
    )
    out = client.search_stations(lat=37.77, lon=-122.42, radius_km=20)
    assert out["stations"][0]["id"] == "12345"
    assert "distance_km" in out["stations"][0]


@respx.mock
def test_rest_token_never_in_error_message():
    token = "super-secret-token-xyz"
    client = BirdWeatherClient(station_token=token, max_retries=1, timeout=5.0)
    respx.get(url__regex=r"https://app\.birdweather\.com/api/v1/stations/.+").mock(
        side_effect=httpx.ConnectError(f"failed connecting with {token}")
    )
    with pytest.raises(BirdWeatherError) as exc:
        client.rest_get("stats", {"period": "all"})
    assert token not in str(exc.value)
    assert "<token>" in str(exc.value)
    client.close()


@respx.mock
def test_rest_stats_on_get_station():
    token = "tok123"
    client = BirdWeatherClient(station_token=token, max_retries=1, timeout=5.0)
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
    respx.get(f"{REST_BASE}{token}/stats").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "detections": 100, "species": 20},
        )
    )
    out = client.get_station(12345)
    assert out["source"] == "graphql+rest"
    assert out["rest_stats"]["detections"] == 100
    client.close()
