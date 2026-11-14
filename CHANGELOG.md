# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3] — 2026-11-14

### Changed

- Migrated to MCP Python SDK 2.x (`MCPServer`; `mcp>=2,<3`).
- DNS rebinding protection is now explicitly on by default (loopback) when `MCP_ALLOWED_HOSTS` is unset.
- `docker/build-push-action` v7 in the image workflow.

### Docs

- PyPI/pipx install documented.

## [0.2.2] — 2026-11-14

### Security

- Compare HTTP bearer tokens with `hmac.compare_digest`; reject websocket scopes when `MCP_AUTH_TOKEN` is set; keep only exact `/health` public.
- Raise `httpx`/`httpcore` loggers to WARNING; install a root logging filter that redacts station and MCP auth tokens (raw and URL-encoded); harden `_redact` and `_err` so unexpected errors never leak token-bearing URLs or tracebacks.
- Warn at startup when HTTP binds a non-loopback host (or `MCP_ALLOWED_HOSTS=*`) without `MCP_AUTH_TOKEN` (still starts for compatibility).
- Validate `station_id`, date windows (max 366 days), species query length, granularity/period enums, and allowlisted REST path segments; keep GraphQL values in variables.
- Run the container as non-root (`USER app`, uid 10001); add `.dockerignore`; tighten compose with `read_only`, `cap_drop: ALL`, `no-new-privileges`, and `/tmp` tmpfs.
- Pin GitHub Actions to full commit SHAs, set `permissions: contents: read`, `persist-credentials: false` on checkout, and add Dependabot for Actions/pip/Docker.
- Expand `SECURITY.md` reporting policy, response expectations, and an HTTP hardening checklist; update configuration and self-hosting docs.

## [0.2.1] — 2026-11-14

### Changed

- Documentation split into focused guides under `docs/` (installation, configuration, clients, tools, self-hosting, development, troubleshooting); README is a concise landing page.
- Homebrew install documented (`brew install pfrederiksen/tap/birdweather-mcp`).

## [0.2.0] — 2026-11-14

### Added

- MCP prompts: `daily_station_summary`, `weekly_report`, `species_deep_dive`.
- MCP resources: `birdweather://station/{station_id}` and `birdweather://station/{station_id}/species`.
- README demo illustration (`docs/assets/demo.svg`) with placeholder Example Station conversation.

### Changed

- Version bump to 0.2.0 consolidating reliability, packaging, analytics tools, and prompts/resources.

## [0.1.4] — 2026-11-14

### Added

- Tools: `species_trend`, `first_of_year` / `new_arrivals`, `compare_stations`, `activity_by_hour` (with unit tests and docs/tools.md entries).
- Detection payloads include `audio_url`, species image/thumbnail URLs, and `spectrogram_url` when the API provides them.

## [0.1.3] — 2026-11-14

### Added

- GitHub Actions workflow to publish multi-arch Docker images to `ghcr.io/pfrederiksen/birdweather-mcp` (`latest` + SHA on `main`; semver on version tags).
- PyPI-oriented packaging metadata and a trusted-publishing release workflow on version tags (configure the publisher on pypi.org; this repo does not publish automatically until that is set up).
- Optional `MCP_AUTH_TOKEN` bearer auth for HTTP mode (`/health` stays open).
- `server.json` for MCP registry metadata and [docs/clients.md](docs/clients.md) for Claude Desktop / Cursor / uvx / HTTP configs.

### Changed

- `docker-compose.yml` and self-hosting / Synology docs prefer pulling the prebuilt GHCR image; build-from-source remains an alternative.

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

[0.2.3]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.2.3
[0.2.2]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.2.2
[0.2.1]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.2.1
[0.2.0]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.2.0
[0.1.4]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.4
[0.1.3]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.3
[0.1.2]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.2
[0.1.1]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.1
[0.1.0]: https://github.com/pfrederiksen/birdweather-mcp/releases/tag/v0.1.0
