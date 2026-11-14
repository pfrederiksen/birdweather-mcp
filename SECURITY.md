# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| 0.2.x   | Yes (when released) |

## Reporting a vulnerability

Please open a [private security advisory](https://github.com/pfrederiksen/birdweather-mcp/security/advisories/new) on GitHub, or email the maintainer listed on the repository. Do not file a public issue for token leaks or remote-exposure bugs.

## Station token handling

`BIRDWEATHER_STATION_TOKEN` unlocks the BirdWeather station REST API (`/api/v1/stations/<token>/...`). Treat it like a password for your station.

This server is designed so that:

- The token is **optional**. Public GraphQL queries work without it.
- The token is read only from the environment (or an explicit client constructor in tests).
- The token is **never written to logs**, tool responses, or error messages. Failures that might contain the raw URL are redacted to `<token>`.
- Example configs in the README use an empty string or omit the variable entirely.

### What you should do

- Prefer env vars or your MCP client's secret store — never hard-code the token in a committed file.
- Keep `.env` out of git (already listed in `.gitignore`). Use `.env.example` as a template.
- For Docker / Synology: inject the token via a mode-`600` `env_file` / host-only `.env` (never inline in compose), not a baked image layer.
- If you suspect a token was exposed, rotate it in the BirdWeather app and update your env.

## Network exposure

The default transport is **stdio** (no open port). If you run **streamable-http**:

- Bind to `127.0.0.1`, a LAN interface, or a Tailscale IP — **not** `0.0.0.0` on a public host unless you have auth in front.
- The compose file maps `127.0.0.1:8000:8000` by design.
- Put a reverse proxy with authentication in front if untrusted clients must reach the MCP endpoint.
- Optional shared-secret gate: set `MCP_AUTH_TOKEN` so `/mcp` requires `Authorization: Bearer …` (`/health` remains open). This is not a substitute for network isolation on the public internet.
- Host-header allowlisting (`MCP_ALLOWED_HOSTS`) defaults to loopback. Set explicit hostnames (or `*` only on trusted networks) when clients use LAN/MagicDNS names; see [docs/self-hosting.md](docs/self-hosting.md).

See [docs/self-hosting.md](docs/self-hosting.md) for LAN / Tailscale / Synology hardening notes.

## Dependencies

Report supply-chain issues the same way as other vulnerabilities. Keep `pip` / `uv` installs current when self-hosting.
