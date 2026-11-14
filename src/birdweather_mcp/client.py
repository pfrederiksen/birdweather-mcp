"""BirdWeather GraphQL + optional station REST clients."""

from __future__ import annotations

import logging
import math
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Self
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from birdweather_mcp import queries
from birdweather_mcp.cache import TTLCache, make_cache_key

logger = logging.getLogger("birdweather_mcp")

GRAPHQL_URL = "https://app.birdweather.com/graphql"
REST_BASE = "https://app.birdweather.com/api/v1/stations/"
USER_AGENT = "birdweather-mcp/0.2.2 (+https://github.com/pfrederiksen/birdweather-mcp)"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
DEFAULT_MAX_RETRIES = 5
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_DETECTION_PAGES = 50  # cap upstream paging for aggregate helpers
MAX_STATION_ID_LEN = 32
MAX_DAYS = 366
MAX_SPECIES_QUERY_LEN = 100
STATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_REST_PATHS = frozenset({"stats", "detections"})
ALLOWED_REST_PERIODS = frozenset({"all", "day", "week", "month", "year"})
ALLOWED_GRANULARITY = frozenset({"day", "week"})


class BirdWeatherError(Exception):
    """User-facing API / input error."""


def _redact(message: str, token: str | None) -> str:
    """Replace raw and URL-encoded token forms in ``message``."""
    if not token:
        return message
    out = message.replace(token, "<token>")
    # Cover both default quote() and quote(..., safe="") encodings.
    for encoded in {quote(token), quote(token, safe="")}:
        if encoded and encoded != token:
            out = out.replace(encoded, "<token>")
    return out


def secrets_from_env() -> list[str]:
    """Station + MCP auth tokens currently present in the environment."""
    secrets: list[str] = []
    for key in ("BIRDWEATHER_STATION_TOKEN", "MCP_AUTH_TOKEN"):
        raw = os.environ.get(key)
        if raw is None:
            continue
        token = raw.strip()
        if token:
            secrets.append(token)
    return secrets


def redact_secrets(message: str, *extra_tokens: str | None) -> str:
    """Redact known secrets (env tokens plus any extras) from a string."""
    out = message
    for token in secrets_from_env():
        out = _redact(out, token)
    for token in extra_tokens:
        out = _redact(out, token)
    return out


def validate_station_id(station_id: str | int) -> str:
    """Validate a station id (non-empty, max 32, ``^[A-Za-z0-9_-]+$``)."""
    text = str(station_id).strip()
    if not text:
        raise BirdWeatherError("station_id must not be empty")
    if len(text) > MAX_STATION_ID_LEN:
        raise BirdWeatherError(
            f"station_id must be at most {MAX_STATION_ID_LEN} characters"
        )
    if not STATION_ID_RE.fullmatch(text):
        raise BirdWeatherError(
            "station_id must match ^[A-Za-z0-9_-]+$ (letters, digits, _, -)"
        )
    return text


def validate_species_query(query: str) -> str:
    text = query.strip()
    if not text:
        raise BirdWeatherError("query must not be empty")
    if len(text) > MAX_SPECIES_QUERY_LEN:
        raise BirdWeatherError(
            f"query must be at most {MAX_SPECIES_QUERY_LEN} characters"
        )
    return text


def _parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise BirdWeatherError(
            f"Invalid date '{value}'. Use ISO dates like YYYY-MM-DD."
        ) from exc


def resolve_timezone(tz_name: str | None, fallback: str = "UTC") -> str:
    name = (tz_name or fallback).strip() or fallback
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise BirdWeatherError(
            f"Unknown timezone '{name}'. Use an IANA name like America/Los_Angeles."
        ) from exc
    return name


def build_period(
    *,
    from_date: str | date | None = None,
    to_date: str | date | None = None,
    days: int | None = None,
    timezone: str | None = None,
    station_timezone: str | None = None,
) -> dict[str, Any]:
    """Build a BirdWeather InputDuration period object."""
    tz = resolve_timezone(timezone or station_timezone or "UTC")
    if days is not None:
        if days < 1:
            raise BirdWeatherError("days must be >= 1")
        if days > MAX_DAYS:
            raise BirdWeatherError(f"days must be <= {MAX_DAYS}")
        if from_date or to_date:
            raise BirdWeatherError("Pass either days or from_date/to_date, not both.")
        end = datetime.now(ZoneInfo(tz)).date()
        start = end - timedelta(days=days - 1)
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "timezone": tz,
        }

    if from_date is None and to_date is None:
        end = datetime.now(ZoneInfo(tz)).date()
        start = end - timedelta(days=6)
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "timezone": tz,
        }

    start = _parse_date(from_date) if from_date else None
    end = _parse_date(to_date) if to_date else None
    if start is None and end is not None:
        start = end
    if end is None and start is not None:
        end = start
    assert start is not None and end is not None
    if end < start:
        raise BirdWeatherError("to_date must be on or after from_date")
    # Inclusive day count: Jan 1–Jan 1 is 1 day; max allowed is MAX_DAYS.
    inclusive_days = (end - start).days + 1
    if inclusive_days > MAX_DAYS:
        raise BirdWeatherError(
            f"date range must not exceed {MAX_DAYS} days (got {inclusive_days})"
        )
    return {"from": start.isoformat(), "to": end.isoformat(), "timezone": tz}


def detection_local_datetime(timestamp: str, timezone: str) -> datetime:
    """Timezone-aware datetime of a detection in the given IANA timezone."""
    text = str(timestamp).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BirdWeatherError(f"Invalid detection timestamp '{timestamp}'") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo(resolve_timezone(timezone)))


def detection_local_date(timestamp: str, timezone: str) -> date:
    """Calendar date of a detection timestamp in the given IANA timezone."""
    return detection_local_datetime(timestamp, timezone).date()


def enrich_detection_media(detection: dict[str, Any]) -> dict[str, Any]:
    """Attach audio/soundscape and spectrogram URL fields when the API provides them.

    GraphQL detections expose ``soundscape.url`` (audio). Species image/thumbnail
    URLs are copied when present. Any spectrogram-like field on the detection,
    soundscape, or REST payload is surfaced as ``spectrogram_url``.
    """
    out = dict(detection)
    soundscape = out.get("soundscape")
    if isinstance(soundscape, dict):
        out["audio_url"] = soundscape.get("url")
        for key in ("spectrogramUrl", "spectrogram_url", "spectrogram"):
            if soundscape.get(key):
                out["spectrogram_url"] = soundscape[key]
                break
    for key in ("spectrogramUrl", "spectrogram_url", "spectrogram"):
        if out.get(key) and "spectrogram_url" not in out:
            val = out[key]
            if isinstance(val, str):
                out["spectrogram_url"] = val
            elif isinstance(val, dict) and val.get("url"):
                out["spectrogram_url"] = val["url"]
            break
    species = out.get("species")
    if isinstance(species, dict):
        if species.get("imageUrl"):
            out.setdefault("species_image_url", species["imageUrl"])
        if species.get("thumbnailUrl"):
            out.setdefault("species_thumbnail_url", species["thumbnailUrl"])
        # REST sometimes uses snake_case
        if species.get("image_url"):
            out.setdefault("species_image_url", species["image_url"])
        if species.get("thumbnail_url"):
            out.setdefault("species_thumbnail_url", species["thumbnail_url"])
    return out


def aggregate_hourly_counts(
    detections: list[dict[str, Any]],
    *,
    period: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bucket detections into station-local hours 0–23 within ``period``."""
    tz_name = resolve_timezone(period.get("timezone"))
    start = _parse_date(period["from"])
    end = _parse_date(period["to"])
    hours = [0] * 24
    for det in detections:
        ts = det.get("timestamp")
        if not ts:
            continue
        local = detection_local_datetime(str(ts), tz_name)
        local_day = local.date()
        if local_day < start or local_day > end:
            continue
        hours[local.hour] += 1
    return [{"hour": h, "count": hours[h]} for h in range(24)]


def rollup_weekly_counts(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Roll day-level totals into ISO weeks (oldest first)."""
    buckets: dict[tuple[int, int], dict[str, Any]] = {}
    for row in daily_rows:
        day = _parse_date(row["date"])
        iso = day.isocalendar()
        key = (iso.year, iso.week)
        entry = buckets.get(key)
        if entry is None:
            buckets[key] = {
                "week": f"{iso.year}-W{iso.week:02d}",
                "from": day.isoformat(),
                "to": day.isoformat(),
                "total": int(row.get("total") or 0),
            }
        else:
            entry["to"] = day.isoformat()
            entry["total"] += int(row.get("total") or 0)
    rows = sorted(buckets.values(), key=lambda r: r["from"])
    return rows


def aggregate_daily_counts(
    detections: list[dict[str, Any]],
    *,
    period: dict[str, Any],
    include_species_breakdown: bool = True,
) -> list[dict[str, Any]]:
    """Bucket detections into station-local calendar days within ``period``.

    BirdWeather's ``dailyDetectionCounts`` GraphQL field buckets by UTC day even
    when a timezone is supplied, and may return an extra following-day row when
    ``from == to``. This helper re-aggregates from detection timestamps instead
    and drops any day outside the requested inclusive range.
    """
    tz_name = resolve_timezone(period.get("timezone"))
    start = _parse_date(period["from"])
    end = _parse_date(period["to"])

    totals: dict[date, int] = {}
    by_species: dict[date, dict[str, dict[str, Any]]] = {}

    for det in detections:
        ts = det.get("timestamp")
        if not ts:
            continue
        local_day = detection_local_date(str(ts), tz_name)
        if local_day < start or local_day > end:
            continue
        totals[local_day] = totals.get(local_day, 0) + 1
        if not include_species_breakdown:
            continue
        species = det.get("species") or {}
        sid = str(det.get("speciesId") or species.get("id") or "")
        if not sid:
            continue
        day_map = by_species.setdefault(local_day, {})
        entry = day_map.get(sid)
        if entry is None:
            day_map[sid] = {
                "count": 1,
                "speciesId": sid,
                "species": {
                    "id": sid,
                    "commonName": species.get("commonName"),
                    "scientificName": species.get("scientificName"),
                },
            }
        else:
            entry["count"] += 1

    rows: list[dict[str, Any]] = []
    day = start
    while day <= end:
        row: dict[str, Any] = {
            "date": day.isoformat(),
            "dayOfYear": day.timetuple().tm_yday,
            "total": totals.get(day, 0),
        }
        if include_species_breakdown:
            counts = list(by_species.get(day, {}).values())
            counts.sort(key=lambda c: (-int(c["count"]), str(c["speciesId"])))
            row["counts"] = counts
        rows.append(row)
        day += timedelta(days=1)

    # Newest first — matches typical BirdWeather dailyDetectionCounts ordering.
    rows.reverse()
    return rows


def bbox_from_point(lat: float, lon: float, radius_km: float) -> tuple[dict, dict]:
    """Approximate NE/SW corners for a radius around a point."""
    if not (-90.0 <= lat <= 90.0):
        raise BirdWeatherError("lat must be between -90 and 90")
    if not (-180.0 <= lon <= 180.0):
        raise BirdWeatherError("lon must be between -180 and 180")
    if radius_km <= 0:
        raise BirdWeatherError("radius_km must be > 0")
    # 1 deg lat ~= 111.32 km; lon shrinks by cos(lat)
    d_lat = radius_km / 111.32
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    d_lon = radius_km / (111.32 * cos_lat)
    ne = {"lat": min(90.0, lat + d_lat), "lon": min(180.0, lon + d_lon)}
    sw = {"lat": max(-90.0, lat - d_lat), "lon": max(-180.0, lon - d_lon)}
    return ne, sw


def _max_retries_from_env(default: int = DEFAULT_MAX_RETRIES) -> int:
    raw = os.environ.get("BIRDWEATHER_MAX_RETRIES")
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _backoff_seconds(attempt: int, *, base: float = 0.5, cap: float = 30.0) -> float:
    """Exponential backoff with full jitter (AWS-style)."""
    exp = min(cap, base * (2**attempt))
    return random.uniform(0, exp)


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.ReadError, httpx.WriteError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return False


class BirdWeatherClient:
    """Thin client over GraphQL (always) and station REST (optional token)."""

    def __init__(
        self,
        *,
        station_token: str | None = None,
        timeout: float = 60.0,
        max_retries: int | None = None,
        client: httpx.Client | None = None,
        cache: TTLCache | None = None,
        use_cache: bool | None = None,
    ) -> None:
        self._token = station_token or os.environ.get("BIRDWEATHER_STATION_TOKEN") or None
        self._timeout = timeout
        self._max_retries = (
            max_retries if max_retries is not None else _max_retries_from_env()
        )
        self._owns_client = client is None
        self._http = client or httpx.Client(
            timeout=timeout,
            headers={"user-agent": USER_AGENT},
        )
        if use_cache is False:
            self._cache: TTLCache | None = None
        elif cache is not None:
            self._cache = cache
        else:
            self._cache = TTLCache.from_env()

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def has_station_token(self) -> bool:
        return bool(self._token)

    @property
    def cache(self) -> TTLCache | None:
        return self._cache

    def _cache_get(self, key: str) -> Any | None:
        if self._cache is None:
            return None
        return self._cache.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        if self._cache is None:
            return
        self._cache.set(key, value)

    def _request_with_retries(
        self,
        *,
        label: str,
        do_request: Any,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp: httpx.Response = do_request()
                if resp.status_code in RETRYABLE_STATUS:
                    wait = _backoff_seconds(attempt)
                    logger.warning(
                        "%s HTTP %s (attempt %s/%s), retrying in %.2fs",
                        label,
                        resp.status_code,
                        attempt + 1,
                        self._max_retries,
                        wait,
                    )
                    if attempt + 1 >= self._max_retries:
                        resp.raise_for_status()
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except BirdWeatherError:
                raise
            except Exception as exc:
                last_error = exc
                if not _is_retryable_http_error(exc):
                    raise BirdWeatherError(
                        f"{label} request failed: {_redact(str(exc), self._token)}"
                    ) from exc
                wait = _backoff_seconds(attempt)
                logger.warning(
                    "%s request failed (attempt %s/%s), retrying in %.2fs: %s",
                    label,
                    attempt + 1,
                    self._max_retries,
                    wait,
                    _redact(str(exc), self._token),
                )
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(wait)
        raise BirdWeatherError(
            f"{label} request failed after retries: "
            f"{_redact(str(last_error), self._token)}"
        )

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        cache_key = make_cache_key("graphql", query, variables)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        payload = {"query": query, "variables": variables}

        def do_request() -> httpx.Response:
            return self._http.post(
                GRAPHQL_URL,
                json=payload,
                headers={"content-type": "application/json"},
            )

        resp = self._request_with_retries(label="GraphQL", do_request=do_request)
        data = resp.json()
        if data.get("errors"):
            msgs = "; ".join(e.get("message", str(e)) for e in data["errors"])
            raise BirdWeatherError(f"GraphQL error: {msgs}")
        if "data" not in data:
            raise BirdWeatherError("GraphQL response missing data")
        result = data["data"]
        self._cache_set(cache_key, result)
        return result

    def rest_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._token:
            raise BirdWeatherError(
                "BIRDWEATHER_STATION_TOKEN is not set; REST endpoints are unavailable."
            )
        # Path segments must be allowlisted constants (never caller-controlled).
        segment = path.lstrip("/")
        if segment not in ALLOWED_REST_PATHS:
            raise BirdWeatherError(f"Invalid REST path '{path}'")
        params = dict(params or {})
        if "period" in params:
            period = str(params["period"])
            if period not in ALLOWED_REST_PERIODS:
                raise BirdWeatherError(
                    f"period must be one of {sorted(ALLOWED_REST_PERIODS)}"
                )
        # Cache key includes a token fingerprint, never the raw token.
        token_fp = make_cache_key("token", self._token)[:16]
        cache_key = make_cache_key("rest", token_fp, segment, params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        # Never put the raw token into log messages.
        url = f"{REST_BASE}{self._token}/{segment}"

        def do_request() -> httpx.Response:
            return self._http.get(url, params=params)

        resp = self._request_with_retries(label="REST", do_request=do_request)
        data = resp.json()
        if data.get("success") is False:
            raise BirdWeatherError(
                f"REST error: {data.get('message') or 'success=false'}"
            )
        self._cache_set(cache_key, data)
        return data

    def get_station(self, station_id: str | int) -> dict[str, Any]:
        sid = validate_station_id(station_id)
        data = self.graphql(queries.STATION, {"id": sid})
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {sid} not found")
        result: dict[str, Any] = {"station": station, "source": "graphql"}
        if self._token:
            try:
                stats = self.rest_get("stats", {"period": "all"})
                result["rest_stats"] = {
                    "detections": stats.get("detections"),
                    "species": stats.get("species"),
                    "period": "all",
                }
                result["source"] = "graphql+rest"
            except BirdWeatherError as exc:
                result["rest_stats_error"] = str(exc)
        return result

    def get_station_timezone(self, station_id: str | int) -> str:
        sid = validate_station_id(station_id)
        data = self.graphql(
            queries.STATION_TIMEZONE,
            {"id": sid},
        )
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {sid} not found")
        return resolve_timezone(station.get("timezone") or "UTC")

    def station_counts(
        self,
        station_id: str | int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        days: int | None = None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        sid = validate_station_id(station_id)
        tz = timezone or self.get_station_timezone(sid)
        period = build_period(
            from_date=from_date, to_date=to_date, days=days, timezone=tz
        )
        data = self.graphql(
            queries.STATION_COUNTS,
            {"id": sid, "period": period},
        )
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {sid} not found")
        return {"station": station, "period": period, "source": "graphql"}

    def get_weather(self, station_id: str | int) -> dict[str, Any]:
        sid = validate_station_id(station_id)
        data = self.graphql(queries.STATION_WEATHER, {"id": sid})
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {sid} not found")
        return {"station": station, "source": "graphql"}

    def resolve_species_id(
        self, species: str | int | None
    ) -> str | None:
        if species is None or species == "":
            return None
        text = str(species).strip()
        if text.isdigit():
            return text
        text = validate_species_query(text)
        # Treat as common or scientific name search; prefer exact common/scientific match.
        results = self.search_species(text, limit=10)
        nodes = results.get("species") or []
        if not nodes:
            raise BirdWeatherError(f"No species found matching '{text}'")
        lowered = text.lower()
        for node in nodes:
            if (node.get("commonName") or "").lower() == lowered:
                return str(node["id"])
            if (node.get("scientificName") or "").lower() == lowered:
                return str(node["id"])
        return str(nodes[0]["id"])

    def recent_detections(
        self,
        station_id: str | int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        days: int | None = None,
        timezone: str | None = None,
        species: str | int | None = None,
        min_confidence: float | None = None,
        limit: int = 25,
        after: str | None = None,
        use_rest: bool | None = None,
    ) -> dict[str, Any]:
        sid = validate_station_id(station_id)
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        tz = timezone or self.get_station_timezone(sid)
        period = build_period(
            from_date=from_date, to_date=to_date, days=days, timezone=tz
        )

        prefer_rest = self._token if use_rest is None else (use_rest and self._token)
        if prefer_rest:
            return self._recent_detections_rest(
                period=period,
                species=species,
                min_confidence=min_confidence,
                limit=limit,
                cursor=after,
            )

        species_id = self.resolve_species_id(species)
        variables: dict[str, Any] = {
            "id": sid,
            "first": limit,
            "after": after,
            "period": period,
            "confidenceGte": min_confidence,
            "sortBy": "timestampDesc",
        }
        if species_id:
            variables["speciesId"] = species_id

        data = self.graphql(queries.DETECTIONS, variables)
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {sid} not found")
        det = station.get("detections") or {}
        nodes = [enrich_detection_media(n) for n in (det.get("nodes") or [])]
        return {
            "station": {"id": station.get("id"), "name": station.get("name"), "timezone": station.get("timezone")},
            "period": period,
            "detections": nodes,
            "total_count": det.get("totalCount"),
            "species_count": det.get("speciesCount"),
            "page_info": det.get("pageInfo"),
            "source": "graphql",
        }

    def _recent_detections_rest(
        self,
        *,
        period: dict[str, Any],
        species: str | int | None,
        min_confidence: float | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        tz = ZoneInfo(period["timezone"])
        start = datetime.combine(_parse_date(period["from"]), datetime.min.time(), tz)
        end = datetime.combine(
            _parse_date(period["to"]) + timedelta(days=1), datetime.min.time(), tz
        ) - timedelta(milliseconds=1)
        params: dict[str, Any] = {
            "limit": limit,
            "from": start.isoformat(timespec="milliseconds"),
            "to": end.isoformat(timespec="milliseconds"),
        }
        if cursor:
            params["cursor"] = cursor

        species_id = self.resolve_species_id(species)
        # REST filter keys are not fully documented; filter client-side when needed.
        page = self.rest_get("detections", params)
        detections = page.get("detections") or []
        filtered = []
        for det in detections:
            sp = det.get("species") or {}
            if species_id and str(sp.get("id") or det.get("speciesId") or "") != species_id:
                continue
            conf = det.get("confidence")
            if min_confidence is not None and conf is not None and conf < min_confidence:
                continue
            filtered.append(det)

        next_cursor = None
        raw = page.get("detections") or []
        if len(raw) >= limit and raw:
            next_cursor = str(raw[-1].get("id"))

        return {
            "period": period,
            "detections": [enrich_detection_media(d) for d in filtered],
            "page_info": {
                "hasNextPage": len(raw) >= limit,
                "endCursor": next_cursor,
            },
            "source": "rest",
        }

    def top_species(
        self,
        station_id: str | int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        days: int | None = None,
        timezone: str | None = None,
        limit: int = 25,
        offset: int = 0,
        species: str | int | None = None,
    ) -> dict[str, Any]:
        sid = validate_station_id(station_id)
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        tz = timezone or self.get_station_timezone(sid)
        period = build_period(
            from_date=from_date, to_date=to_date, days=days, timezone=tz
        )
        species_id = self.resolve_species_id(species)
        variables: dict[str, Any] = {
            "id": sid,
            "limit": limit,
            "offset": offset,
            "period": period,
        }
        if species_id:
            variables["speciesId"] = species_id
        data = self.graphql(queries.TOP_SPECIES, variables)
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {sid} not found")
        return {
            "station": {
                "id": station.get("id"),
                "name": station.get("name"),
                "timezone": station.get("timezone"),
            },
            "period": period,
            "species": station.get("topSpecies") or [],
            "source": "graphql",
        }

    def daily_counts(
        self,
        station_id: str | int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        days: int | None = None,
        timezone: str | None = None,
        species: str | int | None = None,
        include_species_breakdown: bool = True,
    ) -> dict[str, Any]:
        """Per-day totals in the station (or requested) timezone.

        Aggregates detection timestamps into local calendar days rather than
        trusting GraphQL ``dailyDetectionCounts`` (UTC-bucketed, can overshoot
        the requested range).
        """
        sid = validate_station_id(station_id)
        tz = timezone or self.get_station_timezone(sid)
        period = build_period(
            from_date=from_date, to_date=to_date, days=days, timezone=tz
        )
        species_id = self.resolve_species_id(species)
        detections = self._iter_detections(
            sid, period=period, species_id=species_id
        )
        rows = aggregate_daily_counts(
            detections,
            period=period,
            include_species_breakdown=include_species_breakdown,
        )
        return {
            "station_id": sid,
            "period": period,
            "days": rows,
            "source": "graphql",
        }

    def _iter_detections(
        self,
        station_id: str | int,
        *,
        period: dict[str, Any],
        species_id: str | None = None,
        max_pages: int = MAX_DETECTION_PAGES,
        sort_by: str = "timestampDesc",
    ) -> list[dict[str, Any]]:
        """Fetch detections in a period (paginated, capped)."""
        sid = validate_station_id(station_id)
        nodes: list[dict[str, Any]] = []
        after: str | None = None
        pages = max(1, int(max_pages))
        for _ in range(pages):
            variables: dict[str, Any] = {
                "id": sid,
                "first": MAX_PAGE_SIZE,
                "after": after,
                "period": period,
                "sortBy": sort_by,
            }
            if species_id:
                variables["speciesId"] = species_id
            data = self.graphql(queries.DETECTIONS, variables)
            station = data.get("station")
            if not station:
                raise BirdWeatherError(f"Station {sid} not found")
            det = station.get("detections") or {}
            batch = det.get("nodes") or []
            nodes.extend(batch)
            page_info = det.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break
        return nodes

    def species_info(
        self,
        *,
        species_id: str | int | None = None,
        scientific_name: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        sid: str | None = None
        sci: str | None = scientific_name
        if species_id is not None:
            sid = str(species_id)
        elif query and not sci:
            sid = self.resolve_species_id(query)
        elif sci is None and query:
            # allow scientific name via query
            sci = query
        if not sid and not sci:
            raise BirdWeatherError(
                "Provide species_id, scientific_name, or query (common/scientific name)."
            )
        data = self.graphql(
            queries.SPECIES,
            {"id": sid, "scientificName": sci if not sid else None},
        )
        species = data.get("species")
        if not species:
            raise BirdWeatherError("Species not found")
        return {"species": species, "source": "graphql"}

    def search_species(self, query: str, *, limit: int = 20, after: str | None = None) -> dict[str, Any]:
        q = validate_species_query(query if query is not None else "")
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        data = self.graphql(
            queries.SEARCH_SPECIES,
            {"query": q, "first": limit, "after": after},
        )
        conn = data.get("searchSpecies") or {}
        return {
            "species": conn.get("nodes") or [],
            "total_count": conn.get("totalCount"),
            "page_info": conn.get("pageInfo"),
            "source": "graphql",
        }

    def search_stations(
        self,
        *,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: float = 25.0,
        query: str | None = None,
        limit: int = 20,
        after: str | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        variables: dict[str, Any] = {"first": limit, "after": after}
        if query:
            variables["query"] = query
        if lat is not None or lon is not None:
            if lat is None or lon is None:
                raise BirdWeatherError("Provide both lat and lon for geographic search")
            ne, sw = bbox_from_point(lat, lon, radius_km)
            variables["ne"] = ne
            variables["sw"] = sw
        data = self.graphql(queries.STATIONS, variables)
        conn = data.get("stations") or {}
        stations = conn.get("nodes") or []
        if lat is not None and lon is not None:
            for st in stations:
                coords = st.get("coords") or {}
                slat, slon = coords.get("lat"), coords.get("lon")
                if slat is not None and slon is not None:
                    st["distance_km"] = round(
                        _haversine_km(lat, lon, float(slat), float(slon)), 2
                    )
            stations = sorted(
                stations, key=lambda s: s.get("distance_km", float("inf"))
            )
        return {
            "stations": stations,
            "total_count": conn.get("totalCount"),
            "page_info": conn.get("pageInfo"),
            "source": "graphql",
        }

    def species_trend(
        self,
        station_id: str | int,
        species: str | int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        days: int | None = 30,
        timezone: str | None = None,
        granularity: str = "day",
    ) -> dict[str, Any]:
        """Counts over time for one species in station-local time."""
        sid = validate_station_id(station_id)
        gran = (granularity or "day").strip().lower()
        if gran not in ALLOWED_GRANULARITY:
            raise BirdWeatherError("granularity must be 'day' or 'week'")
        species_id = self.resolve_species_id(species)
        if not species_id:
            raise BirdWeatherError("species is required")
        daily = self.daily_counts(
            sid,
            from_date=from_date,
            to_date=to_date,
            days=None if (from_date or to_date) else days,
            timezone=timezone,
            species=species_id,
            include_species_breakdown=False,
        )
        # daily_counts returns newest-first; trend series oldest-first
        day_rows = list(reversed(daily["days"]))
        series = (
            rollup_weekly_counts(day_rows)
            if gran == "week"
            else [{"date": r["date"], "total": r["total"]} for r in day_rows]
        )
        info = self.species_info(species_id=species_id)
        return {
            "station_id": sid,
            "species": info.get("species"),
            "period": daily["period"],
            "granularity": gran,
            "series": series,
            "source": "graphql",
        }

    def _earliest_detection(
        self,
        station_id: str | int,
        *,
        period: dict[str, Any],
        species_id: str,
    ) -> dict[str, Any] | None:
        sid = validate_station_id(station_id)
        data = self.graphql(
            queries.DETECTIONS,
            {
                "id": sid,
                "first": 1,
                "after": None,
                "period": period,
                "speciesId": species_id,
                "sortBy": "timestampAsc",
            },
        )
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {sid} not found")
        nodes = (station.get("detections") or {}).get("nodes") or []
        return nodes[0] if nodes else None

    def first_of_year(
        self,
        station_id: str | int,
        *,
        year: int | None = None,
        since: str | None = None,
        until: str | None = None,
        timezone: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Species whose first detection in a year/season window falls in a range.

        Candidates are species heard in the arrival window (default: last 14 days
        of the season). For each candidate (capped by ``limit``), the earliest
        detection in the season is fetched — one cached GraphQL call per species.
        """
        station = validate_station_id(station_id)
        tz = timezone or self.get_station_timezone(station)
        tz_name = resolve_timezone(tz)
        now_local = datetime.now(ZoneInfo(tz_name)).date()
        if since:
            season_start = _parse_date(since)
            y = season_start.year
        else:
            y = int(year) if year is not None else now_local.year
            if y < 2000 or y > 2100:
                raise BirdWeatherError("year looks invalid")
            season_start = date(y, 1, 1)
        season_end = _parse_date(until) if until else now_local
        if season_end < season_start:
            raise BirdWeatherError("until/to must be on or after since/year start")

        # Arrival window defaults to the last 14 days of the season range.
        arrival_end = season_end
        arrival_start = max(season_start, arrival_end - timedelta(days=13))
        limit = max(1, min(int(limit), 100))

        season = {
            "from": season_start.isoformat(),
            "to": season_end.isoformat(),
            "timezone": tz_name,
        }
        arrival_period = {
            "from": arrival_start.isoformat(),
            "to": arrival_end.isoformat(),
            "timezone": tz_name,
        }
        candidates = self.top_species(
            station,
            from_date=arrival_start.isoformat(),
            to_date=arrival_end.isoformat(),
            timezone=tz_name,
            limit=limit,
        )
        arrivals: list[dict[str, Any]] = []
        for row in candidates.get("species") or []:
            sid = str(row.get("speciesId") or (row.get("species") or {}).get("id") or "")
            if not sid:
                continue
            earliest = self._earliest_detection(
                station, period=season, species_id=sid
            )
            if not earliest or not earliest.get("timestamp"):
                continue
            first_day = detection_local_date(str(earliest["timestamp"]), tz_name)
            if first_day < arrival_start or first_day > arrival_end:
                continue
            species = earliest.get("species") or row.get("species") or {}
            media = enrich_detection_media(earliest)
            arrivals.append(
                {
                    "speciesId": sid,
                    "species": {
                        "id": sid,
                        "commonName": species.get("commonName"),
                        "scientificName": species.get("scientificName"),
                    },
                    "first_detected_on": first_day.isoformat(),
                    "first_timestamp": earliest.get("timestamp"),
                    "detection_id": earliest.get("id"),
                    "soundscape": media.get("soundscape"),
                    "audio_url": media.get("audio_url"),
                    "spectrogram_url": media.get("spectrogram_url"),
                }
            )
        arrivals.sort(key=lambda r: r["first_detected_on"])
        return {
            "station_id": station,
            "year": y,
            "season": season,
            "arrival_window": arrival_period,
            "species": arrivals,
            "candidates_checked": len(candidates.get("species") or []),
            "limit": limit,
            "source": "graphql",
        }

    def new_arrivals(
        self,
        station_id: str | int,
        *,
        year: int | None = None,
        since: str | None = None,
        until: str | None = None,
        timezone: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Alias for :meth:`first_of_year`."""
        return self.first_of_year(
            station_id,
            year=year,
            since=since,
            until=until,
            timezone=timezone,
            limit=limit,
        )

    def compare_stations(
        self,
        station_a: str | int,
        station_b: str | int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        days: int | None = 7,
        timezone: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Species overlap and differences between two stations for a period."""
        validate_station_id(station_a)
        validate_station_id(station_b)
        limit = max(1, min(int(limit), 100))
        a = self.top_species(
            station_a,
            from_date=from_date,
            to_date=to_date,
            days=None if (from_date or to_date) else days,
            timezone=timezone,
            limit=limit,
        )
        # Reuse period/timezone from A for B when timezone was omitted.
        period = a["period"]
        b = self.top_species(
            station_b,
            from_date=period["from"],
            to_date=period["to"],
            timezone=period["timezone"],
            limit=limit,
        )

        def index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
            out: dict[str, dict[str, Any]] = {}
            for row in rows:
                sid = str(row.get("speciesId") or (row.get("species") or {}).get("id") or "")
                if sid:
                    out[sid] = row
            return out

        map_a = index(a.get("species") or [])
        map_b = index(b.get("species") or [])
        ids_a, ids_b = set(map_a), set(map_b)
        shared = sorted(ids_a & ids_b)
        only_a = sorted(ids_a - ids_b)
        only_b = sorted(ids_b - ids_a)

        def brief(row: dict[str, Any]) -> dict[str, Any]:
            sp = row.get("species") or {}
            return {
                "speciesId": str(row.get("speciesId") or sp.get("id")),
                "count": row.get("count"),
                "commonName": sp.get("commonName"),
                "scientificName": sp.get("scientificName"),
            }

        return {
            "period": period,
            "station_a": a.get("station"),
            "station_b": b.get("station"),
            "overlap": [
                {
                    "speciesId": sid,
                    "station_a": brief(map_a[sid]),
                    "station_b": brief(map_b[sid]),
                }
                for sid in shared
            ],
            "only_station_a": [brief(map_a[sid]) for sid in only_a],
            "only_station_b": [brief(map_b[sid]) for sid in only_b],
            "summary": {
                "shared": len(shared),
                "only_a": len(only_a),
                "only_b": len(only_b),
                "limit": limit,
            },
            "source": "graphql",
        }

    def activity_by_hour(
        self,
        station_id: str | int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        days: int | None = 7,
        timezone: str | None = None,
        species: str | int | None = None,
        max_pages: int = 20,
    ) -> dict[str, Any]:
        """Hourly detection histogram in station-local time."""
        sid = validate_station_id(station_id)
        tz = timezone or self.get_station_timezone(sid)
        period = build_period(
            from_date=from_date,
            to_date=to_date,
            days=None if (from_date or to_date) else days,
            timezone=tz,
        )
        species_id = self.resolve_species_id(species)
        detections = self._iter_detections(
            sid,
            period=period,
            species_id=species_id,
            max_pages=max_pages,
        )
        hours = aggregate_hourly_counts(detections, period=period)
        return {
            "station_id": sid,
            "period": period,
            "species_id": species_id,
            "hours": hours,
            "total": sum(h["count"] for h in hours),
            "detections_scanned": len(detections),
            "truncated": len(detections) >= max_pages * MAX_PAGE_SIZE,
            "source": "graphql",
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
