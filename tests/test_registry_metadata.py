"""Unit tests for MCP Registry ownership markers and server.json versions."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_registry_metadata_matches_package_version():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]

    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["name"] == "io.github.pfrederiksen/birdweather-mcp"
    assert server["version"] == version

    packages = {pkg["registryType"]: pkg for pkg in server["packages"]}
    assert packages["pypi"]["version"] == version
    assert packages["oci"]["identifier"] == (
        f"ghcr.io/pfrederiksen/birdweather-mcp:{version}"
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "<!-- mcp-name: io.github.pfrederiksen/birdweather-mcp -->" in readme

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert (
        'LABEL io.modelcontextprotocol.server.name="io.github.pfrederiksen/birdweather-mcp"'
        in dockerfile
    )
