# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-14

### Added

- MCP server with GraphQL tools: `get_station`, `station_counts`, `get_weather`, `recent_detections`, `top_species` / `species_list`, `daily_counts`, `species_info`, `search_species`, `search_stations`.
- Optional `BIRDWEATHER_STATION_TOKEN` for station REST detections and all-time stats (token never logged).
- Transports: `stdio` (default), `streamable-http`, `sse`.
- Dockerfile (`python:3.12-slim`, multi-arch friendly) and `docker-compose.yml` for long-lived HTTP hosting.
- Docs: README, self-hosting guide, tool reference with live samples, contributing, security policy.
- Pytest suite with mocked unit tests and optional `@pytest.mark.live` smoke against public station `12345`.

[0.1.0]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.0
