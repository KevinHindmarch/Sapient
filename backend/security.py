"""Local single-user access control.

The desktop app has one local user and no login. The API listens on 127.0.0.1
only, and every /api request (except /api/health) must carry the per-launch
secret that the Electron shell generated:  ``Authorization: Bearer <token>``.
Requests whose Host header is not a loopback name are refused, which blocks
DNS-rebinding attempts from web pages running in a normal browser.
"""

import os
import secrets

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.database import UserService

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
PUBLIC_PATHS = {"/api/health"}
MIN_TOKEN_LENGTH = 32


def api_token() -> str | None:
    token = os.environ.get("SAPIENT_API_TOKEN", "")
    return token if len(token) >= MIN_TOKEN_LENGTH else None


def _host_name(host_header: str) -> str:
    if host_header.startswith("["):
        return host_header.split("]")[0] + "]"
    return host_header.rsplit(":", 1)[0] if ":" in host_header else host_header


class LocalAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or request.method == "OPTIONS":
            return await call_next(request)
        if _host_name(request.headers.get("host", "")).lower() not in LOOPBACK_HOSTS:
            return JSONResponse({"detail": "Sapient only accepts local connections"}, status_code=403)
        if path in PUBLIC_PATHS:
            return await call_next(request)
        expected = api_token()
        if expected is None:
            return JSONResponse({"detail": "Sapient API token is not configured"}, status_code=503)
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
            return JSONResponse({"detail": "Invalid or missing Sapient API token"}, status_code=401)
        return await call_next(request)


def get_current_user() -> dict:
    """The single local user. Access was already checked by LocalAccessMiddleware."""
    user = UserService.get_local_user()
    if user is None:
        raise HTTPException(503, "Local profile is not initialised")
    return user
