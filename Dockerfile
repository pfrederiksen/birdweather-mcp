# Multi-arch friendly: python:3.12-slim publishes linux/amd64 and linux/arm64.
# Build for Synology / Raspberry Pi / Apple Silicon:
#   docker buildx build --platform linux/arm64 -t birdweather-mcp --load .
# Multi-platform (registry push):
#   docker buildx build --platform linux/amd64,linux/arm64 -t you/birdweather-mcp:latest --push .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd -r -u 10001 app

USER app

LABEL io.modelcontextprotocol.server.name="io.github.pfrederiksen/birdweather-mcp"

ENV MCP_TRANSPORT=stdio
# Optional: BIRDWEATHER_STATION_TOKEN for station REST API (never logged)
# Optional: MCP_AUTH_TOKEN for HTTP bearer auth (never logged)
# Do not bake secrets into the image — pass them at runtime.

EXPOSE 8000

# Passes immediately for stdio; GET /health for HTTP transports (no upstream call).
# Compose also defines a healthcheck — see docker-compose.yml.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,sys,urllib.request; t=os.environ.get('MCP_TRANSPORT','stdio'); sys.exit(0) if t in ('stdio','') else urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('MCP_PORT','8000'), timeout=2)"

ENTRYPOINT ["birdweather-mcp"]
CMD []
