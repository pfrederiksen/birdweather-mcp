# Multi-arch friendly: python:3.12-slim publishes linux/amd64 and linux/arm64.
# Build for Synology / Raspberry Pi / Apple Silicon:
#   docker buildx build --platform linux/arm64 -t birdweather-mcp --load .
# Multi-platform (registry push):
#   docker buildx build --platform linux/amd64,linux/arm64 -t you/birdweather-mcp:latest --push .

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=stdio
# Optional: BIRDWEATHER_STATION_TOKEN for station REST API (never logged)

EXPOSE 8000

# Passes immediately for stdio; checks the listen port for HTTP transports.
# Compose also defines a healthcheck — see docker-compose.yml.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,socket,sys; t=os.environ.get('MCP_TRANSPORT','stdio'); sys.exit(0) if t in ('stdio','') else socket.create_connection(('127.0.0.1', int(os.environ.get('MCP_PORT','8000'))), 2).close()"

ENTRYPOINT ["birdweather-mcp"]
CMD []
