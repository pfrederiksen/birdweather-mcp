"""Optional bearer-token gate for HTTP MCP transports."""

from __future__ import annotations

import os
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = frozenset({"/health"})


def auth_token_from_env() -> str | None:
    raw = os.environ.get("MCP_AUTH_TOKEN")
    if raw is None:
        return None
    token = raw.strip()
    return token or None


def _header_value(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> str | None:
    for key, value in headers:
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except UnicodeDecodeError:
                return None
    return None


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


class BearerAuthMiddleware:
    """Require ``Authorization: Bearer <MCP_AUTH_TOKEN>`` except public paths.

    When ``expected_token`` is empty/None, all requests pass through.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        expected_token: str | None,
        public_paths: frozenset[str] = PUBLIC_PATHS,
    ) -> None:
        self.app = app
        self.expected_token = (expected_token or "").strip() or None
        self.public_paths = public_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.expected_token:
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if path in self.public_paths:
            await self.app(scope, receive, send)
            return

        authorization = _header_value(scope.get("headers") or [], b"authorization")
        presented = extract_bearer_token(authorization)
        if presented is not None and presented == self.expected_token:
            await self.app(scope, receive, send)
            return

        body = b'{"error":"unauthorized"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"www-authenticate", b'Bearer realm="birdweather-mcp"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def wrap_app_with_optional_auth(app: ASGIApp) -> ASGIApp:
    token = auth_token_from_env()
    if not token:
        return app
    return BearerAuthMiddleware(app, expected_token=token)
