"""BirdWeather MCP server (FastMCP / stdio by default)."""

from __future__ import annotations

import argparse
import ipaddress
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
from birdweather_mcp.client import (
    BirdWeatherClient,
    BirdWeatherError,
    redact_secrets,
    validate_station_id,
)

logger = logging.getLogger("birdweather_mcp")


class TokenRedactFilter(logging.Filter):
    """Redact station and MCP auth tokens from log records (raw + URL-encoded)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        redacted = redact_secrets(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def install_token_redact_filter() -> None:
    """Install a redacting filter on the root logger and its current handlers."""
    filt = TokenRedactFilter()
    root = logging.getLogger()
    root.addFilter(filt)
    for handler in root.handlers:
        handler.addFilter(filt)


def is_loopback_host(host: str) -> bool:
    """Return True when ``host`` is clearly loopback-only."""
    text = (host or "").strip().lower()
    if not text:
        return False
    if text in {"localhost", "127.0.0.1", "::1", "[::1]"}:
        return True
    # Strip brackets used for IPv6 literals.
    candidate = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def warn_insecure_http_defaults(*, host: str, transport: str) -> None:
    """Log prominent warnings for risky HTTP defaults (do not refuse to start)."""
    if transport not in {"streamable-http", "sse"}:
        return
    token = auth_token_from_env()
    if not token and not is_loopback_host(host):
        logger.warning(
            "SECURITY: HTTP transport bound to non-loopback host %r without "
            "MCP_AUTH_TOKEN. Set MCP_AUTH_TOKEN so /mcp requires "
            "Authorization: Bearer <token> ( /health stays public).",
            host,
        )
    allowed = (os.environ.get("MCP_ALLOWED_HOSTS") or "").strip()
    if allowed == "*" and not token:
        logger.warning(
            "SECURITY: MCP_ALLOWED_HOSTS=* with no MCP_AUTH_TOKEN disables "
            "DNS rebinding protection and leaves /mcp unauthenticated. "
            "Set MCP_AUTH_TOKEN on trusted networks."
        )

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
        return json.dumps({"error": redact_secrets(str(exc))}, indent=2)
    # Never log a traceback that might embed a token-bearing URL; redact instead.
    safe = redact_secrets(f"{type(exc).__name__}: {exc}")
    logger.error("Unexpected error: %s", safe)
    return json.dumps({"error": safe}, indent=2)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> Response:
    """Cheap liveness probe for streamable-HTTP (no upstream BirdWeather call)."""
    return JSONResponse({"status": "ok", "version": __version__})


@mcp.prompt()
def daily_station_summary(station_id: str = "12345") -> str:
    """Prompt: summarize today's activity at a station."""
    sid = validate_station_id(station_id)
    return (
        f"Using birdweather-mcp tools, summarize today's bird activity at station "
        f"{sid}. Call get_station, station_counts (days=1), top_species "
        f"(days=1, limit=10), and recent_detections (days=1, limit=10). "
        f"Mention timezone, top species, notable high-confidence detections, and "
        f"any soundscape/audio URLs. Use placeholder-friendly wording if data is sparse."
    )


@mcp.prompt()
def weekly_report(station_id: str = "12345") -> str:
    """Prompt: weekly detection report for a station."""
    sid = validate_station_id(station_id)
    return (
        f"Produce a weekly report for BirdWeather station {sid}. "
        f"Use station_counts (days=7), top_species (days=7, limit=15), "
        f"daily_counts (days=7, include_species_breakdown=false), and "
        f"activity_by_hour (days=7). Summarize totals, busiest days/hours, "
        f"dominant species, and any new_arrivals for the current year."
    )


@mcp.prompt()
def species_deep_dive(station_id: str = "12345", species: str = "House Finch") -> str:
    """Prompt: deep-dive one species at a station."""
    sid = validate_station_id(station_id)
    return (
        f"Deep-dive on {species} at station {sid}. "
        f"Call species_info (query={species!r}), species_trend "
        f"(days=30, granularity=day), recent_detections (days=7, species={species!r}, "
        f"limit=10), and activity_by_hour (days=7, species={species!r}). "
        f"Explain trend shape, typical hours, and link audio/soundscape URLs when present."
    )


@mcp.resource(
    "birdweather://station/{station_id}",
    name="station_info",
    title="Station info",
    description="JSON station metadata for a BirdWeather station id.",
    mime_type="application/json",
)
def station_info_resource(station_id: str) -> str:
    """Resource: station metadata JSON."""
    try:
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(client.get_station(sid))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.resource(
    "birdweather://station/{station_id}/species",
    name="station_species_list",
    title="Station species list",
    description="JSON top species for the last 7 days at a station.",
    mime_type="application/json",
)
def station_species_list_resource(station_id: str) -> str:
    """Resource: recent species list JSON (7-day window)."""
    try:
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(client.top_species(sid, days=7, limit=50))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def get_station(station_id: str) -> str:
    """Get station metadata: name, location, coords, timezone, detection range, thresholds.

    If BIRDWEATHER_STATION_TOKEN is set, also includes all-time REST stats.
    """
    try:
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(client.get_station(sid))
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(
                client.station_counts(
                    sid,
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(client.get_weather(sid))
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(
                client.recent_detections(
                    sid,
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(
                client.top_species(
                    sid,
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(
                client.daily_counts(
                    sid,
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(
                client.species_trend(
                    sid,
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(
                client.first_of_year(
                    sid,
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
        a = validate_station_id(station_a)
        b = validate_station_id(station_b)
        with _client() as client:
            return _ok(
                client.compare_stations(
                    a,
                    b,
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
        sid = validate_station_id(station_id)
        with _client() as client:
            return _ok(
                client.activity_by_hour(
                    sid,
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
    # Avoid httpx/httpcore INFO request-URL logs (REST embeds the station token).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    install_token_redact_filter()
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

    warn_insecure_http_defaults(host=args.host, transport=args.transport)
    _install_optional_http_auth()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
