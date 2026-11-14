FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=stdio
# Optional: BIRDWEATHER_STATION_TOKEN for station REST API (never logged)

EXPOSE 8000

ENTRYPOINT ["birdweather-mcp"]
CMD []
