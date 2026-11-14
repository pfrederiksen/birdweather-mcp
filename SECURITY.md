# Security Policy

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 0.2.x   | Yes (latest)       |
| < 0.2   | No                 |

## Reporting a vulnerability

Please use **GitHub private vulnerability reporting** via this repository’s
[Security tab](https://github.com/pfrederiksen/birdweather-mcp/security/advisories/new)
(New draft security advisory). Do **not** open a public issue for token leaks,
auth bypasses, or remote-exposure bugs.

### Response expectations

- Acknowledgement of a valid report is typically within **7 days**.
- We aim to share an initial assessment and remediation plan within **14 days**.
- Fixes for actively exploitable issues in the supported `0.2.x` line are
  prioritized for a patch release when practical.
- Please give us a reasonable window to ship a fix before any public disclosure.

## Station token handling

`BIRDWEATHER_STATION_TOKEN` unlocks the BirdWeather station REST API
(`/api/v1/stations/<token>/...`). Treat it like a password for your station.

This server is designed so that:

- The token is **optional**. Public GraphQL queries work without it.
- The token is read only from the environment (or an explicit client constructor in tests).
- The token is **never written to logs**, tool responses, or error messages. Failures that might contain the raw URL are redacted to `<token>` (including URL-encoded forms). `httpx`/`httpcore` request URL logging is kept at WARNING+.
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
- Optional shared-secret gate: set `MCP_AUTH_TOKEN` so `/mcp` requires `Authorization: Bearer …` (`/health` remains open, exact path only). This is not a substitute for network isolation on the public internet.
- Host-header allowlisting (`MCP_ALLOWED_HOSTS`) defaults to loopback. Set explicit hostnames (or `*` only on trusted networks) when clients use LAN/MagicDNS names; see [docs/self-hosting.md](docs/self-hosting.md).
- At startup, binding HTTP to a non-loopback host (or setting `MCP_ALLOWED_HOSTS=*`) without `MCP_AUTH_TOKEN` logs a prominent WARNING. The process still starts for backward compatibility.

### HTTP deployment hardening checklist

- [ ] Set `MCP_AUTH_TOKEN` and require `Authorization: Bearer …` for `/mcp`
- [ ] Set `MCP_ALLOWED_HOSTS` to explicit hostnames (avoid `*` unless the network is fully trusted)
- [ ] Bind/publish to **LAN or loopback only** (compose default: `127.0.0.1:8000:8000`)
- [ ] Run the **non-root** container image (`USER app`, uid `10001`); prefer compose `read_only`, `cap_drop: ALL`, `no-new-privileges`
- [ ] Keep secrets in a mode-`600` `.env` / secret store — never bake tokens into images
- [ ] Place a reverse proxy with TLS + auth in front if clients are not on a trusted network

See [docs/self-hosting.md](docs/self-hosting.md) for LAN / Tailscale / Synology hardening notes.

## Dependencies

Report supply-chain issues the same way as other vulnerabilities. Keep `pip` / `uv` installs current when self-hosting. GitHub Dependabot watches Actions, pip, and Docker weekly.
