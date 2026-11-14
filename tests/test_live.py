"""Optional live smoke tests against the public BirdWeather GraphQL API.

Requires BIRDWEATHER_TEST_STATION_ID (a public numeric station id).
Skipped when that env var is unset.

Run with: BIRDWEATHER_TEST_STATION_ID=<STATION_ID> pytest -m live
"""

from __future__ import annotations

import os

import pytest

from birdweather_mcp.client import BirdWeatherClient

STATION_ID = os.environ.get("BIRDWEATHER_TEST_STATION_ID", "").strip()

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not STATION_ID,
        reason="BIRDWEATHER_TEST_STATION_ID not set",
    ),
]


@pytest.fixture(scope="module")
def live_client():
    c = BirdWeatherClient(max_retries=3, timeout=60.0)
    yield c
    c.close()


def test_live_get_station(live_client: BirdWeatherClient):
    out = live_client.get_station(STATION_ID)
    station = out["station"]
    assert station["id"] == STATION_ID
    assert station.get("timezone")
    assert station.get("coords")


def test_live_recent_detections(live_client: BirdWeatherClient):
    out = live_client.recent_detections(
        STATION_ID, days=2, limit=5, min_confidence=0.5
    )
    assert "detections" in out
    assert out["source"] == "graphql"
    # Station may be quiet — schema/shape is what matters.
    for det in out["detections"]:
        assert "timestamp" in det
        assert "species" in det or "speciesId" in det


def test_live_top_species(live_client: BirdWeatherClient):
    out = live_client.top_species(STATION_ID, days=14, limit=5)
    assert isinstance(out["species"], list)
    if out["species"]:
        assert out["species"][0]["species"]["commonName"]
        assert out["species"][0]["count"] >= 1


def test_live_daily_counts(live_client: BirdWeatherClient):
    out = live_client.daily_counts(
        STATION_ID, days=3, include_species_breakdown=False
    )
    assert isinstance(out["days"], list)


def test_live_search_stations_near_test_station(live_client: BirdWeatherClient):
    station = live_client.get_station(STATION_ID)["station"]
    coords = station.get("coords") or {}
    lat, lon = coords.get("lat"), coords.get("lon")
    assert lat is not None and lon is not None
    out = live_client.search_stations(
        lat=lat, lon=lon, radius_km=30, limit=5
    )
    assert out["stations"]
    for st in out["stations"]:
        assert st.get("coords")


def test_live_species_info_raven(live_client: BirdWeatherClient):
    out = live_client.species_info(scientific_name="Corvus corax")
    assert out["species"]["commonName"] == "Common Raven"
