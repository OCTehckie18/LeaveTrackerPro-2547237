"""Request-id + access log + baseline security headers.

Pure ASGI (not BaseHTTPMiddleware) so streaming responses and contextvars behave.
Also: the Origin check (CSRF layer 2) and an early body-size limit.
"""

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.core.logging import request_id_var

log = logging.getLogger("app.access")

SECURITY_HEADERS = {
    # API responses are JSON or files, never pages: lock everything down.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = rid
                docs = scope["path"].startswith(("/api/docs", "/api/openapi"))
                for key, value in SECURITY_HEADERS.items():
                    if docs and key == "Content-Security-Policy":
                        continue
                    headers.setdefault(key, value)
                if "server" in headers:
                    del headers["server"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)


_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class OriginCheckMiddleware:
    """CSRF defence in depth (SameSite=Strict is layer one): a browser-made state-changing
    request must come from one of our own origins."""

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed = set(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in _MUTATING:
            headers = dict(scope["headers"])
            origin = headers.get(b"origin", b"").decode()
            site = headers.get(b"sec-fetch-site", b"").decode()
            bad_origin = bool(origin) and origin.rstrip("/") not in self.allowed
            bad_site = not origin and bool(site) and site not in ("same-origin", "none")
            if bad_origin or bad_site:
                resp = error_response(
                    "FORBIDDEN", "This request didn't come from the LeaveTrackerPro app."
                )
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """Reject oversized uploads early using Content-Length (nginx / Vercel enforce it too)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            length = dict(scope["headers"]).get(b"content-length", b"0")
            if length.isdigit() and int(length) > self.max_bytes:
                resp = error_response(
                    "PAYLOAD_TOO_LARGE",
                    "That upload is too large. Try smaller files, or a PDF instead of a photo.",
                )
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)
