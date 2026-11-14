# Troubleshooting & FAQ

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Client shows no tools | Confirm `uvx` / `uv` / `brew` is on the PATH the GUI app sees; restart the client after config edits |
| `Station … not found` | Check the numeric id in the BirdWeather URL; try `search_stations` |
| Empty detections | Widen `days`, lower `min_confidence`, or confirm the station is active |
| REST / token errors | Token only needed for REST extras; leave unset for GraphQL. Rotate if leaked |
| HTTP client can't connect | Use `http://host:8000/mcp`, bind/publish carefully — see [self-hosting.md](self-hosting.md) |
| `421 Invalid Host header` | Set `MCP_ALLOWED_HOSTS` to the hostname clients use (e.g. `nas.example.local:*`) or `*` on trusted nets — see [configuration.md](configuration.md) |
| Docker arm64 “exec format” | Pull the multi-arch GHCR image, or import a `linux/arm64` image built with buildx (never build on a low-RAM NAS) |
| Container unhealthy | `docker compose logs`; ensure `MCP_TRANSPORT=streamable-http` |
| Token not taking effect | Restart after editing `.env`; confirm `env_file` is used |

Self-hosting-specific symptoms (Synology error 2202, `scp -O`, Tailscale userspace) are covered in [self-hosting.md](self-hosting.md#troubleshooting).

## FAQ

**Do I need my own BirdWeather station?**  
No. Any public station id works with GraphQL. A token only unlocks REST for *your* station.

**Is the token sent to the LLM?**  
Tool results do not include the token. Keep it in env/config only; don’t paste it into chat.

**Where do I find my station ID?**  
Open your station on [app.birdweather.com](https://app.birdweather.com); the URL is `…/stations/<id>`. Docs use placeholders like `12345` — substitute your own. Details: [configuration.md](configuration.md#finding-a-station-id-and-token).

**Can I expose this on the internet?**  
Not recommended without auth. Prefer Tailscale / LAN bind. Details in [SECURITY.md](../SECURITY.md) and [self-hosting.md](self-hosting.md).

**Which install method should I use?**  
Desktop clients: [uvx or Homebrew](installation.md). Always-on NAS: [Docker/GHCR](self-hosting.md).
