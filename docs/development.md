# Development

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/pfrederiksen/birdweather-mcp.git
cd birdweather-mcp
uv sync --dev
```

Do not commit real `BIRDWEATHER_STATION_TOKEN` or personal station ids. Use a local `.env` (gitignored); start from `.env.example`.

## Run the server

```bash
# stdio (default)
uv run birdweather-mcp

# HTTP for local debugging
uv run birdweather-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

## Tests

```bash
# unit tests (mocked network — default; CI uses -m "not live")
uv run pytest -q
# or explicitly:
uv run pytest -m "not live"

# optional live smoke against public GraphQL (skipped if unset)
BIRDWEATHER_TEST_STATION_ID=12345 uv run pytest -m live
```

Use any **public** station id for live tests; docs use `12345` as a placeholder shape only.

## Lint

```bash
uv run ruff check .
```

## Project layout

```text
src/birdweather_mcp/
  server.py      # MCPServer (MCP Python SDK 2.x) tools, prompts, resources, CLI, /health
  client.py      # GraphQL + optional station REST
  queries.py     # GraphQL query strings
  cache.py       # In-memory TTL cache
  auth.py        # Optional MCP_AUTH_TOKEN bearer gate
docs/            # Installation, config, clients, tools, self-hosting, …
tests/           # Unit tests + optional @pytest.mark.live
.github/workflows/
  ci.yml               # ruff + unit tests
  docker-publish.yml   # GHCR multi-arch on main + tags
  publish-pypi.yml     # PyPI trusted publishing on version tags
server.json      # MCP registry metadata
docker-compose.yml
```

## Guidelines

- Prefer clear tool descriptions and stable JSON shapes over breaking response changes.
- Keep token redaction intact in `client.py` (`_redact`, no token in log format strings).
- Add or update unit tests for new tools / period edge cases.
- Document new tools in [tools.md](tools.md) (include a sample payload when practical).
- Do not commit the local `reference/` folder.

## Release process

1. **Bump version** in lockstep:
   - `pyproject.toml` (`[project].version`)
   - `src/birdweather_mcp/__init__.py` (`__version__`)
   - `server.json` (top-level `version` and package version fields, including the GHCR tag)
   - `uv.lock` (project version pin) — run `uv lock` if needed
2. **CHANGELOG.md** — add a Keep a Changelog entry for `X.Y.Z` with the release date.
3. **Commit** on `main` (or a short-lived release branch merged to `main`).
4. **Tag** `vX.Y.Z` and push the tag (maintainers only). That triggers:
   - **GHCR** (`.github/workflows/docker-publish.yml`): multi-arch `linux/amd64` + `linux/arm64` image `ghcr.io/pfrederiksen/birdweather-mcp` tagged with semver (`X.Y.Z`, `X.Y`) plus `latest` / SHA on `main`.
   - **PyPI** (`.github/workflows/publish-pypi.yml`): `uv build` + trusted publishing is configured and runs on `vX.Y.Z` tags (no API token secret in the workflow).
5. **Homebrew tap** — update the formula in `pfrederiksen/homebrew-tap` (version, URL/sha256 for the release tarball or PyPI sdist) so `brew install pfrederiksen/tap/birdweather-mcp` tracks the new release.

Do not publish tags from documentation-only dry runs unless you intend to ship.

## Pull requests

1. Fork / branch from `main`.
2. Keep the diff scoped; update docs when behavior changes.
3. Ensure `uv run ruff check .` and `uv run pytest -q` pass.
4. Open a PR with a short summary of *why* the change exists.

## Code of conduct

Be respectful. Birdwatching and open source both work better that way.
