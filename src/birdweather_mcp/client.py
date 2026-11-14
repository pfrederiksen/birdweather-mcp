"""BirdWeather GraphQL + optional station REST clients."""

from __future__ import annotations

import logging
import math
import os
import random
import time
from datetime import date, datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from birdweather_mcp import queries
from birdweather_mcp.cache import TTLCache, make_cache_key

logger = logging.getLogger("birdweather_mcp")

GRAPHQL_URL = "https://app.birdweather.com/graphql"
REST_BASE = "https://app.birdweather.com/api/v1/stations/"
USER_AGENT = "birdweather-mcp/0.2 (+https://github.com/pfrederiksen/birdweather-mcp)"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
DEFAULT_MAX_RETRIES = 5
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_DETECTION_PAGES = 50  # cap upstream paging for aggregate helpers


class BirdWeatherError(Exception):
    """User-facing API / input error."""


def _redact(message: str, token: str | None) -> str:
    if not token:
        return message
    return message.replace(token, "<token>")


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
    return {"from": start.isoformat(), "to": end.isoformat(), "timezone": tz}


def detection_local_date(timestamp: str, timezone: str) -> date:
    """Calendar date of a detection timestamp in the given IANA timezone."""
    text = str(timestamp).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BirdWeatherError(f"Invalid detection timestamp '{timestamp}'") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo(resolve_timezone(timezone))).date()


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
        params = params or {}
        # Cache key includes a token fingerprint, never the raw token.
        token_fp = make_cache_key("token", self._token)[:16]
        cache_key = make_cache_key("rest", token_fp, path, params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        # Never put the raw token into log messages.
        url = f"{REST_BASE}{self._token}/{path.lstrip('/')}"

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
        data = self.graphql(queries.STATION, {"id": str(station_id)})
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {station_id} not found")
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
        data = self.graphql(
            "query($id: ID!){ station(id:$id){ timezone } }",
            {"id": str(station_id)},
        )
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {station_id} not found")
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
        tz = timezone or self.get_station_timezone(station_id)
        period = build_period(
            from_date=from_date, to_date=to_date, days=days, timezone=tz
        )
        data = self.graphql(
            queries.STATION_COUNTS,
            {"id": str(station_id), "period": period},
        )
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {station_id} not found")
        return {"station": station, "period": period, "source": "graphql"}

    def get_weather(self, station_id: str | int) -> dict[str, Any]:
        data = self.graphql(queries.STATION_WEATHER, {"id": str(station_id)})
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {station_id} not found")
        return {"station": station, "source": "graphql"}

    def resolve_species_id(
        self, species: str | int | None
    ) -> str | None:
        if species is None or species == "":
            return None
        text = str(species).strip()
        if text.isdigit():
            return text
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
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        tz = timezone or self.get_station_timezone(station_id)
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
            "id": str(station_id),
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
            raise BirdWeatherError(f"Station {station_id} not found")
        det = station.get("detections") or {}
        return {
            "station": {"id": station.get("id"), "name": station.get("name"), "timezone": station.get("timezone")},
            "period": period,
            "detections": det.get("nodes") or [],
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
            "detections": filtered,
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
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        tz = timezone or self.get_station_timezone(station_id)
        period = build_period(
            from_date=from_date, to_date=to_date, days=days, timezone=tz
        )
        species_id = self.resolve_species_id(species)
        variables: dict[str, Any] = {
            "id": str(station_id),
            "limit": limit,
            "offset": offset,
            "period": period,
        }
        if species_id:
            variables["speciesId"] = species_id
        data = self.graphql(queries.TOP_SPECIES, variables)
        station = data.get("station")
        if not station:
            raise BirdWeatherError(f"Station {station_id} not found")
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
        tz = timezone or self.get_station_timezone(station_id)
        period = build_period(
            from_date=from_date, to_date=to_date, days=days, timezone=tz
        )
        species_id = self.resolve_species_id(species)
        detections = self._iter_detections(
            station_id, period=period, species_id=species_id
        )
        rows = aggregate_daily_counts(
            detections,
            period=period,
            include_species_breakdown=include_species_breakdown,
        )
        return {
            "station_id": str(station_id),
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
    ) -> list[dict[str, Any]]:
        """Fetch detections in a period (paginated, capped)."""
        nodes: list[dict[str, Any]] = []
        after: str | None = None
        pages = max(1, int(max_pages))
        for _ in range(pages):
            variables: dict[str, Any] = {
                "id": str(station_id),
                "first": MAX_PAGE_SIZE,
                "after": after,
                "period": period,
                "sortBy": "timestampDesc",
            }
            if species_id:
                variables["speciesId"] = species_id
            data = self.graphql(queries.DETECTIONS, variables)
            station = data.get("station")
            if not station:
                raise BirdWeatherError(f"Station {station_id} not found")
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
        if not query or not query.strip():
            raise BirdWeatherError("query must not be empty")
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        data = self.graphql(
            queries.SEARCH_SPECIES,
            {"query": query.strip(), "first": limit, "after": after},
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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
