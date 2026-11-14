# Contributing

Thanks for helping improve birdweather-mcp. Small, focused PRs are welcome.

Development setup, tests, lint, project layout, and the release process are documented in **[docs/development.md](docs/development.md)**.

```bash
git clone https://github.com/pfrederiksen/birdweather-mcp.git
cd birdweather-mcp
uv sync --dev
uv run pytest -q
uv run ruff check .
```

Requires Python 3.11+. Do not commit real `BIRDWEATHER_STATION_TOKEN` or personal station ids.
