# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] — 2026-11-14

### Added

- In-memory TTL response cache for GraphQL and REST (`BIRDWEATHER_CACHE_TTL`, `BIRDWEATHER_CACHE_MAX_ENTRIES`, `BIRDWEATHER_CACHE_ENABLED`).
- Retries with exponential backoff and jitter on HTTP 429/5xx and timeouts (`BIRDWEATHER_MAX_RETRIES`).
- `GET /health` liveness endpoint in streamable-HTTP mode (no upstream call); Dockerfile and compose healthchecks use it.
- GitHub Actions CI: ruff + unit tests on Python 3.11–3.13 (no live tests).

## [0.1.1] — 2026-11-14

### Fixed

- `daily_counts` now aggregates detections into station-local calendar days (GraphQL `dailyDetectionCounts` buckets by UTC and can return an extra day when `from == to`). Rows outside the requested range are omitted; quiet days are included with `total: 0`.

### Added

- `MCP_ALLOWED_HOSTS` for streamable-HTTP Host-header allowlisting (comma-separated, or `*` on trusted networks) to avoid `421 Invalid Host header` when clients use LAN/MagicDNS names.

### Changed

- Synology self-hosting docs: off-NAS `linux/arm64` buildx + image import, `env_file` for tokens, LAN bind + MagicDNS, Container Manager / error 2202 notes, free-port and folder-layout examples.

## [0.1.0] — 2026-11-14

### Added

- MCP server with GraphQL tools: `get_station`, `station_counts`, `get_weather`, `recent_detections`, `top_species` / `species_list`, `daily_counts`, `species_info`, `search_species`, `search_stations`.
- Optional `BIRDWEATHER_STATION_TOKEN` for station REST detections and all-time stats (token never logged).
- Transports: `stdio` (default), `streamable-http`, `sse`.
- Dockerfile (`python:3.12-slim`, multi-arch friendly) and `docker-compose.yml` for long-lived HTTP hosting.
- Docs: README, self-hosting guide, tool reference with live samples, contributing, security policy.
- Pytest suite with mocked unit tests and optional `@pytest.mark.live` smoke (set `BIRDWEATHER_TEST_STATION_ID`).

[0.1.2]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.2
[0.1.1]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.1
[0.1.0]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.0
