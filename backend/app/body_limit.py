"""Request body size cap, enforced before any route reads the body.

Each upload route checks its own file size, but only after the framework has
already received the whole body, so an oversized request still costs the
server the time and disk to take it in. This refuses it up front: at once when
Content-Length declares too much, and mid-stream when a chunked body runs past
the cap.
"""

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

# Routes that take a bulk archive rather than a single file.
ARCHIVE_PATHS = frozenset({"/api/backup/import", "/api/export/flights/import/log"})

# Multipart framing (boundaries, part headers, small form fields) on top of
# the file itself.
FORM_OVERHEAD = 1024 * 1024


def body_limit_for(path: str) -> int:
    """The largest request body accepted on this path, in bytes."""
    base = settings.MAX_ARCHIVE_SIZE if path in ARCHIVE_PATHS else settings.MAX_UPLOAD_SIZE
    return base + FORM_OVERHEAD


def _too_large(limit: int) -> str:
    return f"Request body too large (max {limit // (1024 * 1024)}MB)"


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodySizeLimitMiddleware:
    """Pure ASGI middleware, so it sees the body stream rather than a buffered copy."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = body_limit_for(scope["path"])
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            response = JSONResponse({"detail": _too_large(limit)}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # An HTTPException passes through FastAPI's body parsing
                    # untouched (anything else becomes a 400) and is turned
                    # into the 413 response by the exception handler.
                    raise HTTPException(413, _too_large(limit))
            return message

        await self.app(scope, counted_receive, send)
