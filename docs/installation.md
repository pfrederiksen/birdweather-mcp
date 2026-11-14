# Installation

Pick one path below. For MCP client wiring after install, see [clients.md](clients.md). For long-lived HTTP on a NAS, see [self-hosting.md](self-hosting.md).

## Requirements & compatibility

- **Python 3.11+**
- From **0.2.3**, the package requires `mcp>=2,<3` (MCP Python SDK 2.x). If your environment pins `mcp` 1.x, either install in an isolated environment (`pipx`, `uvx`, Homebrew, or Docker avoid the conflict) or pin `pip install birdweather-mcp==0.2.2` (last release on `mcp` 1.x). See [troubleshooting](troubleshooting.md#troubleshooting) for pip resolver conflicts.

## uvx (recommended for desktop clients)

No clone required:

```bash
uvx birdweather-mcp
```

From git if you prefer the latest commit:

```bash
uvx --from git+https://github.com/pfrederiksen/birdweather-mcp birdweather-mcp
```

## pip (PyPI)

```bash
pip install birdweather-mcp
birdweather-mcp
# equivalent: python -m birdweather_mcp
```

From a local checkout:

```bash
pip install .
birdweather-mcp
```

## pipx

```bash
pipx install birdweather-mcp
birdweather-mcp
```

## Homebrew

```bash
brew install pfrederiksen/tap/birdweather-mcp
birdweather-mcp
```

## Docker / GHCR

Prebuilt multi-arch images (`linux/amd64`, `linux/arm64`):

```bash
docker pull ghcr.io/pfrederiksen/birdweather-mcp:latest
```

**stdio** (MCP clients that spawn the container):

```bash
docker run --rm -i ghcr.io/pfrederiksen/birdweather-mcp:latest
```

**streamable-HTTP** (always-on / NAS):

```bash
docker compose pull && docker compose up -d
# MCP endpoint: http://127.0.0.1:8000/mcp
```

See [self-hosting.md](self-hosting.md) for compose, Synology, and hardening.

## From source (uv)

```bash
git clone https://github.com/pfrederiksen/birdweather-mcp.git
cd birdweather-mcp
uv sync
uv run birdweather-mcp
```

For a full developer setup (tests, lint, layout), see [development.md](development.md).

## Transports

| Transport | Use case |
|-----------|----------|
| `stdio` (default) | Claude Desktop, Cursor, VS Code, Claude Code |
| `streamable-http` | Remote / Docker / Synology (`http://host:8000/mcp`) |
| `sse` | Legacy SSE clients |

```bash
uv run birdweather-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Override via env: `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT` — see [configuration.md](configuration.md).
