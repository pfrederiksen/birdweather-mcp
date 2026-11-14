"""BirdWeather MCP server (FastMCP / stdio by default)."""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from birdweather_mcp import __version__
from birdweather_mcp.auth import auth_token_from_env, wrap_app_with_optional_auth
from birdweather_mcp.client import BirdWeatherClient, BirdWeatherError

logger = logging.getLogger("birdweather_mcp")

# FastMCP defaults — keep when MCP_ALLOWED_HOSTS is unset.
_DEFAULT_ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
]

mcp = FastMCP(
    "birdweather",
    instructions=(
        "Query BirdWeather stations: detections, top species, daily counts, "
        "species trends, new arrivals, station comparison, hourly activity, "
        "species info, and nearby stations. Public GraphQL needs no auth. "
        "Set BIRDWEATHER_STATION_TOKEN for richer station REST data. "
        "Use IANA timezones (e.g. America/Los_Angeles). Station IDs are numeric "
        "(see app.birdweather.com/stations/<id>)."
    ),
)


def parse_allowed_hosts(raw: str | None) -> list[str] | None:
    """Parse ``MCP_ALLOWED_HOSTS``.

    Returns:
      - ``None`` if unset/empty (caller should keep FastMCP defaults)
      - ``[]`` when ``*`` (disable DNS rebinding protection / allow any host)
      - otherwise a list of Host header patterns (comma-separated)
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text == "*":
        return []
    hosts = [part.strip() for part in text.split(",") if part.strip()]
    return hosts or None


def transport_security_from_env(
    raw_hosts: str | None = None,
) -> TransportSecuritySettings | None:
    """Build transport security settings from ``MCP_ALLOWED_HOSTS``.

    - Unset: return ``None`` (leave FastMCP defaults alone).
    - ``*``: disable DNS rebinding protection (trusted networks only).
    - Comma-separated hosts: enable protection with those hosts plus loopback
      defaults. Patterns like ``hostname:*`` allow any port. Matching
      ``http(s)://…`` origin patterns are derived automatically.
    """
    if raw_hosts is None:
        raw_hosts = os.environ.get("MCP_ALLOWED_HOSTS")
    parsed = parse_allowed_hosts(raw_hosts)
    if parsed is None:
        return None
    if parsed == []:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    hosts = list(dict.fromkeys([*_DEFAULT_ALLOWED_HOSTS, *parsed]))
    origins = list(_DEFAULT_ALLOWED_ORIGINS)
    for host in parsed:
        if host.endswith(":*"):
            base = host[:-2]
            origins.append(f"http://{base}:*")
            origins.append(f"https://{base}:*")
        else:
            origins.append(f"http://{host}")
            origins.append(f"https://{host}")
    origins = list(dict.fromkeys(origins))
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


def _client() -> BirdWeatherClient:
    return BirdWeatherClient()


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)


def _err(exc: Exception) -> str:
    if isinstance(exc, BirdWeatherError):
        return json.dumps({"error": str(exc)}, indent=2)
    logger.exception("Unexpected error")
    return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, indent=2)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> Response:
    """Cheap liveness probe for streamable-HTTP (no upstream BirdWeather call)."""
    return JSONResponse({"status": "ok", "version": __version__})


@mcp.tool()
def get_station(station_id: str) -> str:
    """Get station metadata: name, location, coords, timezone, detection range, thresholds.

    If BIRDWEATHER_STATION_TOKEN is set, also includes all-time REST stats.
    """
    try:
        with _client() as client:
            return _ok(client.get_station(station_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def station_counts(
    station_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 7,
    timezone: str | None = None,
) -> str:
    """Detection and unique-species counts for a station over a period.

    Prefer `days` (default 7) or an explicit from_date/to_date (YYYY-MM-DD).
    Timezone defaults to the station's timezone.
    """
    try:
        with _client() as client:
            return _ok(
                client.station_counts(
                    station_id,
                    from_date=from_date,
                    to_date=to_date,
                    days=None if (from_date or to_date) else days,
                    timezone=timezone,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def get_weather(station_id: str) -> str:
    """Current weather reading for a station, when BirdWeather has one."""
    try:
        with _client() as client:
            return _ok(client.get_weather(station_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def recent_detections(
    station_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 1,
    timezone: str | None = None,
    species: str | None = None,
    min_confidence: float | None = None,
    limit: int = 25,
    after: str | None = None,
) -> str:
    """List recent detections for a station.

    Filters: optional species (id, common name, or scientific name), min_confidence (0–1),
    and a time window via days (default 1) or from_date/to_date. Use `after` with the
    previous page_info.endCursor for pagination. When BIRDWEATHER_STATION_TOKEN is set,
    the station REST API is preferred (extra fields like image URLs).
    """
    try:
        with _client() as client:
            return _ok(
                client.recent_detections(
                    station_id,
                    from_date=from_date,
                    to_date=to_date,
                    days=None if (from_date or to_date) else days,
                    timezone=timezone,
                    species=species,
                    min_confidence=min_confidence,
                    limit=limit,
                    after=after,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def top_species(
    station_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 7,
    timezone: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> str:
    """Top species by detection count for a station and period (species_list)."""
    try:
        with _client() as client:
            return _ok(
                client.top_species(
                    station_id,
                    from_date=from_date,
                    to_date=to_date,
                    days=None if (from_date or to_date) else days,
                    timezone=timezone,
                    limit=limit,
                    offset=offset,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def species_list(
    station_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 7,
    timezone: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Alias for top_species: species heard at a station in a period, ranked by count."""
    return top_species(
        station_id=station_id,
        from_date=from_date,
        to_date=to_date,
        days=days,
        timezone=timezone,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
def daily_counts(
    station_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 7,
    timezone: str | None = None,
    species: str | None = None,
    include_species_breakdown: bool = True,
) -> str:
    """Per-day detection totals (and optional per-species breakdown) for a station."""
    try:
        with _client() as client:
            return _ok(
                client.daily_counts(
                    station_id,
                    from_date=from_date,
                    to_date=to_date,
                    days=None if (from_date or to_date) else days,
                    timezone=timezone,
                    species=species,
                    include_species_breakdown=include_species_breakdown,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def species_info(
    species_id: str | None = None,
    scientific_name: str | None = None,
    query: str | None = None,
) -> str:
    """Species profile: names, eBird/Wikipedia links, images, summary.

    Look up by species_id, scientific_name, or a free-text query (common or scientific name).
    """
    try:
        with _client() as client:
            return _ok(
                client.species_info(
                    species_id=species_id,
                    scientific_name=scientific_name,
                    query=query,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def search_species(query: str, limit: int = 20, after: str | None = None) -> str:
    """Search BirdWeather's species catalog by common or scientific name fragment."""
    try:
        with _client() as client:
            return _ok(client.search_species(query, limit=limit, after=after))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def search_stations(
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 25.0,
    query: str | None = None,
    limit: int = 20,
    after: str | None = None,
) -> str:
    """Find stations near a lat/lon (default 25 km radius) and/or by name query.

    Geographic results include distance_km from the search point, sorted nearest-first.
    """
    try:
        with _client() as client:
            return _ok(
                client.search_stations(
                    lat=lat,
                    lon=lon,
                    radius_km=radius_km,
                    query=query,
                    limit=limit,
                    after=after,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def species_trend(
    station_id: str,
    species: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 30,
    timezone: str | None = None,
    granularity: str = "day",
) -> str:
    """Counts over time for one species at a station (station-local days or weeks)."""
    try:
        with _client() as client:
            return _ok(
                client.species_trend(
                    station_id,
                    species,
                    from_date=from_date,
                    to_date=to_date,
                    days=None if (from_date or to_date) else days,
                    timezone=timezone,
                    granularity=granularity,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def first_of_year(
    station_id: str,
    year: int | None = None,
    since: str | None = None,
    until: str | None = None,
    timezone: str | None = None,
    limit: int = 50,
) -> str:
    """Species whose first detection of the year (or season) falls in the arrival window.

    Default arrival window is the last 14 days of the season (Jan 1–today, or since/until).
    """
    try:
        with _client() as client:
            return _ok(
                client.first_of_year(
                    station_id,
                    year=year,
                    since=since,
                    until=until,
                    timezone=timezone,
                    limit=limit,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def new_arrivals(
    station_id: str,
    year: int | None = None,
    since: str | None = None,
    until: str | None = None,
    timezone: str | None = None,
    limit: int = 50,
) -> str:
    """Alias for first_of_year: new species arrivals in the recent arrival window."""
    return first_of_year(
        station_id=station_id,
        year=year,
        since=since,
        until=until,
        timezone=timezone,
        limit=limit,
    )


@mcp.tool()
def compare_stations(
    station_a: str,
    station_b: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 7,
    timezone: str | None = None,
    limit: int = 100,
) -> str:
    """Compare species lists for two stations over the same period (overlap and uniques)."""
    try:
        with _client() as client:
            return _ok(
                client.compare_stations(
                    station_a,
                    station_b,
                    from_date=from_date,
                    to_date=to_date,
                    days=None if (from_date or to_date) else days,
                    timezone=timezone,
                    limit=limit,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def activity_by_hour(
    station_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    days: int | None = 7,
    timezone: str | None = None,
    species: str | None = None,
) -> str:
    """Hourly detection histogram in station-local time (optional species filter)."""
    try:
        with _client() as client:
            return _ok(
                client.activity_by_hour(
                    station_id,
                    from_date=from_date,
                    to_date=to_date,
                    days=None if (from_date or to_date) else days,
                    timezone=timezone,
                    species=species,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def _install_optional_http_auth() -> None:
    """Wrap HTTP ASGI apps with bearer auth when ``MCP_AUTH_TOKEN`` is set."""
    if not auth_token_from_env():
        return

    _orig_streamable = mcp.streamable_http_app
    _orig_sse = mcp.sse_app

    def streamable_http_app_with_auth():
        return wrap_app_with_optional_auth(_orig_streamable())

    def sse_app_with_auth(mount_path: str | None = None):
        return wrap_app_with_optional_auth(_orig_sse(mount_path))

    mcp.streamable_http_app = streamable_http_app_with_auth  # type: ignore[method-assign]
    mcp.sse_app = sse_app_with_auth  # type: ignore[method-assign]
    logger.info(
        "HTTP bearer auth enabled (MCP_AUTH_TOKEN set; /health remains open)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BirdWeather MCP server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "127.0.0.1"),
        help="Host for HTTP transports",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "8000")),
        help="Port for HTTP transports",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Never log env token values.
    if os.environ.get("BIRDWEATHER_STATION_TOKEN"):
        logger.info("Station REST API enabled (token present, not logged)")

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    security = transport_security_from_env()
    if security is not None:
        mcp.settings.transport_security = security
        if not security.enable_dns_rebinding_protection:
            logger.info(
                "DNS rebinding protection disabled (MCP_ALLOWED_HOSTS=*); "
                "use only on trusted networks"
            )
        else:
            logger.info(
                "Allowed Host headers: %s",
                ", ".join(security.allowed_hosts),
            )

    _install_optional_http_auth()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
