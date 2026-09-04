"""OpenAPI response schema helpers for documenting HTTPException responses."""

DESCRIPTIONS = {
    400: "Bad request",
    401: "Not authenticated",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    429: "Too many requests",
}


def responses(*codes: int) -> dict:
    """Generate an OpenAPI responses dict for the given HTTP status codes."""
    return {code: {"description": DESCRIPTIONS.get(code, "Error")} for code in codes}
