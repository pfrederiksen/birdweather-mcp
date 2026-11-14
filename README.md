# birdweather-mcp

Self-hostable [MCP](https://modelcontextprotocol.io) server for [BirdWeather](https://www.birdweather.com) stations. Clone it, run it locally, and plug it into Claude Desktop, Cursor, or any MCP client to query detections, species, and station stats.

Uses the public GraphQL API at `https://app.birdweather.com/graphql` (no auth). Optionally set `BIRDWEATHER_STATION_TOKEN` for the station REST API (`/api/v1/stations/<token>/...`) for richer fields. **The token is never logged or echoed.**

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Install & run

```bash
# one-shot via uvx (from GitHub)
uvx --from git+https://github.com/pfrederiksen/birdweather-mcp birdweather-mcp

# or clone and run locally
git clone https://github.com/pfrederiksen/birdweather-mcp.git
cd birdweather-mcp
uv sync
uv run birdweather-mcp

# or with pip
pip install .
birdweather-mcp
# equivalent: python -m birdweather_mcp
```

### Transports

- **stdio** (default) — what Claude Desktop and Cursor expect
- **streamable-http** — optional HTTP for remote/local debugging

```bash
uv run birdweather-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

### Docker

```bash
docker build -t birdweather-mcp .
docker run --rm -i birdweather-mcp
# optional token + HTTP:
docker run --rm -e BIRDWEATHER_STATION_TOKEN -e MCP_TRANSPORT=streamable-http -p 8000:8000 birdweather-mcp --transport streamable-http --host 0.0.0.0
```

## Configure MCP clients

### Claude Desktop

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`):

```json
{
  "mcpServers": {
    "birdweather": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/pfrederiksen/birdweather-mcp", "birdweather-mcp"],
      "env": {
        "BIRDWEATHER_STATION_TOKEN": ""
      }
    }
  }
}
```

Omit `BIRDWEATHER_STATION_TOKEN` (or leave it empty) if you only need the public GraphQL API. For a local checkout:

```json
{
  "mcpServers": {
    "birdweather": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/birdweather-mcp", "birdweather-mcp"]
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` (project) or Cursor MCP settings:

```json
{
  "mcpServers": {
    "birdweather": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/pfrederiksen/birdweather-mcp", "birdweather-mcp"]
    }
  }
}
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BIRDWEATHER_STATION_TOKEN` | No | Station API token from BirdWeather. Enables REST detections/stats. Never logged. |
| `MCP_TRANSPORT` | No | `stdio` (default), `streamable-http`, or `sse` |
| `MCP_HOST` / `MCP_PORT` | No | Bind address for HTTP transports (default `127.0.0.1:8000`) |

## Tools

| Tool | Description |
|------|-------------|
| `get_station` | Station name, coords, timezone, detection range, thresholds; REST all-time stats if token set |
| `station_counts` | Detection + unique-species counts for a period |
| `get_weather` | Latest weather reading for a station (when available) |
| `recent_detections` | Detections with time window, species filter, min confidence, limit, cursor pagination |
| `top_species` / `species_list` | Ranked species for a station/period |
| `daily_counts` | Per-day totals with optional per-species breakdown |
| `species_info` | Species profile (names, eBird/Wikipedia, images, summary) |
| `search_species` | Search the species catalog |
| `search_stations` | Stations near lat/lon (radius) and/or by name |

### Period defaults

- Dates are `YYYY-MM-DD` in the station timezone (or an explicit IANA timezone).
- `days=N` means the last N calendar days including today in that timezone.
- If neither `days` nor dates are given, tools that need a window typically default to 1 day (`recent_detections`) or 7 days (counts / top species).

### Example: west Example City station

Station **12345** (`America/Los_Angeles`) is a convenient public example for docs and tests—not hardcoded in the server.

Ask your MCP client things like:

- “What species has station 12345 heard in the last 7 days?”
- “Show recent House Finch detections at 12345 with confidence ≥ 0.7”
- “Find BirdWeather stations within 20 km of 40.0, -105.0”

## Tests

```bash
uv sync --dev
uv run pytest                 # unit tests (mocked network)
uv run pytest -m live         # optional live smoke against the public API (station 12345)
```

## API references

- GraphQL: https://app.birdweather.com/graphql
- Schema docs: https://app.birdweather.com/api/index.html
- Station REST (token): `https://app.birdweather.com/api/v1/stations/<token>/...`

## License

MIT
