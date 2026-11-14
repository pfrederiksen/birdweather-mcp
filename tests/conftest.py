"""Shared fixtures."""

from __future__ import annotations

import pytest

from birdweather_mcp.client import BirdWeatherClient


@pytest.fixture
def client():
    c = BirdWeatherClient(max_retries=1, station_token=None, timeout=10.0)
    yield c
    c.close()
