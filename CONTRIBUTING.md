# Contributing

Thanks for helping improve birdweather-mcp. Small, focused PRs are welcome.

## Setup

```bash
git clone https://github.com/pfrederiksen/birdweather-mcp.git
cd birdweather-mcp
uv sync --dev
```

Requires Python 3.11+.

## Development loop

```bash
# run the MCP server (stdio)
uv run birdweather-mcp

# HTTP for local debugging
uv run birdweather-mcp --transport streamable-http --host 127.0.0.1 --port 8000

# unit tests (mocked network — default; CI uses -m "not live")
uv run pytest -m "not live"

# lint
uv run ruff check src tests

# optional live smoke against public GraphQL
# Set BIRDWEATHER_TEST_STATION_ID to a public station id; tests skip if unset.
BIRDWEATHER_TEST_STATION_ID=<STATION_ID> uv run pytest -m live
```

Do not commit real `BIRDWEATHER_STATION_TOKEN` or personal station ids. Use `.env` locally (gitignored).

## Guidelines

- Prefer clear tool descriptions and stable JSON shapes over breaking response changes.
- Keep token redaction intact in `client.py` (`_redact`, no token in log format strings).
- Add or update unit tests for new tools / period edge cases.
- Document new tools in `README.md` and `docs/tools.md` (include a sample payload when practical).
- Do not commit the local `reference/` folder.

## Pull requests

1. Fork / branch from `main`.
2. Keep the diff scoped; update docs when behavior changes.
3. Ensure `uv run pytest` passes.
4. Open a PR with a short summary of *why* the change exists.

## Code of conduct

Be respectful. Birdwatching and open source both work better that way.
