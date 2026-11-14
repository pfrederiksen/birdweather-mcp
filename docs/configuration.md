# Configuration

All settings are environment variables (or CLI flags that mirror the transport trio). Copy [`.env.example`](../.env.example) for a local template. **Never commit real tokens.**

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BIRDWEATHER_STATION_TOKEN` | No | unset | Station API token for REST detections / all-time stats. **Never logged.** Without it, public GraphQL only. |
| `MCP_TRANSPORT` | No | `stdio` | `stdio`, `streamable-http`, or `sse`. Overridable with `--transport`. |
| `MCP_HOST` | No | `127.0.0.1` | Bind host for HTTP transports. Overridable with `--host`. Inside Docker use `0.0.0.0` and restrict with host port publish (prefer `127.0.0.1` or LAN-only on the host). Non-loopback bind without `MCP_AUTH_TOKEN` logs a SECURITY warning. |
| `MCP_PORT` | No | `8000` | Bind port for HTTP transports. Overridable with `--port`. |
| `MCP_ALLOWED_HOSTS` | No | unset (loopback only) | Comma-separated Host header patterns for streamable-HTTP DNS-rebinding protection (e.g. `nas.example.local:*,192.168.1.10:*`). Unset = FastMCP loopback defaults. `*` = allow any host (**trusted networks only**; warns if `MCP_AUTH_TOKEN` is unset). Fixes `421 Invalid Host header` for MagicDNS/LAN names. |
| `MCP_AUTH_TOKEN` | No | unset | When set, HTTP `/mcp` requires `Authorization: Bearer …` (constant-time compare). Exact `/health` stays open; websockets are rejected. Strongly recommended for non-loopback HTTP. Never logged. |
| `BIRDWEATHER_CACHE_TTL` | No | `60` | In-memory upstream cache TTL in seconds. Set `0` to disable. |
| `BIRDWEATHER_CACHE_MAX_ENTRIES` | No | `256` | Max cached GraphQL/REST responses. |
| `BIRDWEATHER_CACHE_ENABLED` | No | enabled when TTL &gt; 0 | Set `false` / `0` / `no` / `off` to disable caching; `true` / `1` / `yes` / `on` to force on. |
| `BIRDWEATHER_MAX_RETRIES` | No | `5` | Retries with exponential backoff + jitter on HTTP 429/5xx and timeouts (minimum effective value `1`). |
| `BIRDWEATHER_TEST_STATION_ID` | No | unset | Public station id for optional live pytest (`pytest -m live`). Prefer shell-only; do not commit a personal id. |

### Logging

The server logs to stderr at **INFO** with format `%(levelname)s %(name)s: %(message)s`. There is no log-level env var today. Station and MCP auth tokens are **never** written to logs or tool/error payloads (raw and URL-encoded forms are redacted via a logging filter; `httpx`/`httpcore` are set to WARNING so request URLs are not printed). See [SECURITY.md](../SECURITY.md).

### Health endpoint

In `streamable-http` mode, `GET /health` returns `{"status":"ok","version":"..."}` with **no** upstream BirdWeather call. Used by Docker/compose healthchecks. Unaffected by `MCP_AUTH_TOKEN` (exact path only — `/health/../mcp` is not public).

## Finding a station ID and token

**Station ID** (public, numeric — docs use `12345`):

1. Open your station on [app.birdweather.com](https://app.birdweather.com) (web) or in the BirdWeather app.
2. Check the URL: `https://app.birdweather.com/stations/<id>` — that number is `station_id`.
3. Or search by name/coords with the `search_stations` tool once the server is running.

**Station token** (secret — optional):

1. In the BirdWeather app or web UI, open **your** station’s settings.
2. Find the **API / token** section (used for `https://app.birdweather.com/api/v1/stations/<token>/...`).
3. Copy into `BIRDWEATHER_STATION_TOKEN` in MCP config or `.env` — never commit it.

Without a token, all GraphQL tools still work for any public station. With a token, `get_station` can include all-time REST stats and `recent_detections` prefers REST (extra fields).

## CLI flags

```bash
birdweather-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

| Flag | Env equivalent |
|------|----------------|
| `--transport` | `MCP_TRANSPORT` |
| `--host` | `MCP_HOST` |
| `--port` | `MCP_PORT` |

## Related

- [Clients](clients.md) — where to put env in Claude / Cursor / HTTP
- [Self-hosting](self-hosting.md) — Docker, Synology, `MCP_ALLOWED_HOSTS`
- [Troubleshooting](troubleshooting.md)
