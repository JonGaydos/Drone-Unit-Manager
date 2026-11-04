"""Request body size cap, enforced before any route reads the body.

Each upload route checks its own file size, but only after the framework has
already received the whole body, so an oversized request still costs the
server the time and disk to take it in. This refuses it up front: at once when
Content-Length declares too much, and mid-stream when a chunked body runs past
the cap. A route not named here gets the default, which no ordinary form or
record comes near.
"""

import re


from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

# Routes that take a bulk archive rather than a single file.
ARCHIVE_PATHS = frozenset({"/api/backup/import", "/api/export/flights/import/log"})

# Routes that take one file. Paths are written as their routes are, so a parameter
# matches one path segment. test_every_file_route_is_on_the_upload_list keeps this
# complete.
UPLOAD_PATHS = frozenset({
    "/api/documents/upload",
    "/api/export/excel/import",
    "/api/export/flights/import",
    "/api/import/commit",
    "/api/import/preview",
    "/api/photos/upload",
    "/api/pilots/{pilot_id}/photo",
    "/api/settings/logo",
    "/api/vehicles/{vehicle_id}/photo",
})

# JSON routes whose ordinary requests can pass the default.
LARGE_JSON_PATHS = frozenset({
    # The reports page sends the logo inside the request, as base64, and a logo
    # may be as large as any upload.
    "/api/reports/generate",
    # polygon_points has no upper bound, and a boundary traced from survey data
    # can run past the 25,000 or so vertices that fit in the default.
    "/api/geofences",
    "/api/geofences/{geofence_id}",
})

DEFAULT_BODY_LIMIT = 1024 * 1024

# Multipart framing (boundaries, part headers, small form fields) on top of
# the file itself.
FORM_OVERHEAD = 1024 * 1024


_SINGLE_FILE_SIZED = re.compile(
    "|".join(re.sub(r"\{\w+\}", "[^/]+", path) for path in sorted(UPLOAD_PATHS | LARGE_JSON_PATHS))
)


def body_limit_for(path: str) -> int:
    """The largest request body accepted on this path, in bytes. A trailing slash
    still reaches the route, through its redirect, so it counts as the same path."""
    path = path.removesuffix("/")
    if path in ARCHIVE_PATHS:
        return settings.MAX_ARCHIVE_SIZE + FORM_OVERHEAD
    if _SINGLE_FILE_SIZED.fullmatch(path):
        return settings.MAX_UPLOAD_SIZE + FORM_OVERHEAD
    return DEFAULT_BODY_LIMIT


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
