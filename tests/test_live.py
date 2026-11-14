"""Optional live smoke tests against the public BirdWeather GraphQL API.

Run with: pytest -m live
"""

from __future__ import annotations

import pytest

from birdweather_mcp.client import BirdWeatherClient

# Public example station (west Example City). Not hardcoded in the server.
EXAMPLE_STATION_ID = "12345"


pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_client():
    c = BirdWeatherClient(max_retries=3, timeout=60.0)
    yield c
    c.close()


def test_live_get_station(live_client: BirdWeatherClient):
    out = live_client.get_station(EXAMPLE_STATION_ID)
    station = out["station"]
    assert station["id"] == EXAMPLE_STATION_ID
    assert station.get("timezone")
    assert station.get("coords")


def test_live_recent_detections(live_client: BirdWeatherClient):
    out = live_client.recent_detections(
        EXAMPLE_STATION_ID, days=2, limit=5, min_confidence=0.5
    )
    assert "detections" in out
    assert out["source"] == "graphql"
    # Station is active; expect at least some activity over two days, but
    # don't fail hard if the window is quiet — schema/shape is what matters.
    for det in out["detections"]:
        assert "timestamp" in det
        assert "species" in det or "speciesId" in det


def test_live_top_species(live_client: BirdWeatherClient):
    out = live_client.top_species(EXAMPLE_STATION_ID, days=14, limit=5)
    assert isinstance(out["species"], list)
    if out["species"]:
        assert out["species"][0]["species"]["commonName"]
        assert out["species"][0]["count"] >= 1


def test_live_daily_counts(live_client: BirdWeatherClient):
    out = live_client.daily_counts(
        EXAMPLE_STATION_ID, days=3, include_species_breakdown=False
    )
    assert isinstance(out["days"], list)


def test_live_search_stations_near_vegas(live_client: BirdWeatherClient):
    out = live_client.search_stations(
        lat=40.0, lon=-105.0, radius_km=30, limit=5
    )
    assert out["stations"]
    ids = {s["id"] for s in out["stations"]}
    # Nearby search should usually include the example station, but coords/privacy
    # can vary — just ensure we got stations with coords.
    for st in out["stations"]:
        assert st.get("coords")
    assert ids  # non-empty


def test_live_species_info_raven(live_client: BirdWeatherClient):
    out = live_client.species_info(scientific_name="Corvus corax")
    assert out["species"]["commonName"] == "Common Raven"
