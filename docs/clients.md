# MCP client configurations

Configure Claude Desktop, Cursor, and other MCP clients to talk to birdweather-mcp over **stdio** (local process), **uvx** / Homebrew, or **streamable-HTTP** (self-hosted Docker / NAS).

Use placeholder station id `12345` in prompts. Never put a real `BIRDWEATHER_STATION_TOKEN` or `MCP_AUTH_TOKEN` in committed files. Env reference: [configuration.md](configuration.md). Install paths: [installation.md](installation.md).

## stdio via uvx (recommended for desktop clients)

```json
{
  "mcpServers": {
    "birdweather": {
      "command": "uvx",
      "args": ["birdweather-mcp"]
    }
  }
}
```

From git:

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

## stdio via Homebrew

After `brew install pfrederiksen/tap/birdweather-mcp`:

```json
{
  "mcpServers": {
    "birdweather": {
      "command": "birdweather-mcp"
    }
  }
}
```

Optional env:

```json
{
  "mcpServers": {
    "birdweather": {
      "command": "uvx",
      "args": ["birdweather-mcp"],
      "env": {
        "BIRDWEATHER_STATION_TOKEN": ""
      }
    }
  }
}
```

## stdio via local checkout

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

## Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the Windows equivalent. Use either uvx block above under `mcpServers`.

## Cursor

Project `.cursor/mcp.json` or Cursor MCP settings — same `mcpServers` shape as Claude Desktop.

## Claude Code

```bash
claude mcp add birdweather -- uvx birdweather-mcp
# or from git:
claude mcp add birdweather -- uvx --from git+https://github.com/pfrederiksen/birdweather-mcp birdweather-mcp
```

## VS Code

`.vscode/mcp.json`:

```json
{
  "servers": {
    "birdweather": {
      "type": "stdio",
      "command": "uvx",
      "args": ["birdweather-mcp"]
    }
  }
}
```

## streamable-HTTP (Docker / Synology / LAN)

Run the server (see [self-hosting.md](self-hosting.md)), then point the client at `/mcp`:

```json
{
  "mcpServers": {
    "birdweather": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

If `MCP_AUTH_TOKEN` is set on the server, send a bearer header (exact client support varies):

```json
{
  "mcpServers": {
    "birdweather": {
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer <your-mcp-auth-token>"
      }
    }
  }
}
```

`GET /health` stays unauthenticated for probes. Prefer LAN / Tailscale over public exposure — see [SECURITY.md](../SECURITY.md).

## Registry metadata

[`server.json`](../server.json) describes this server for the official MCP registry (PyPI + GHCR package entries). Publishing to the registry is a separate step after PyPI/GHCR packages exist.
