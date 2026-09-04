"""API token generation and request authentication.

Tokens look like "dum_<43 url-safe chars>" so they are distinguishable from
login JWTs at a glance. Only the SHA-256 hash is stored. Every request
authenticated by a token is checked against the token's read_only flag and
area scopes; any path outside the scope map (auth, settings, users, backup,
sync, audit, the token API itself) is denied to all tokens.
"""

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.api_token import ApiToken
from app.models.user import User

TOKEN_PREFIX = "dum_"

# API areas selectable when creating a token, mapped to route prefixes.
# A request path must fall under one of the token's areas to be allowed.
SCOPE_PREFIXES = {
    "fleet": [
        "/api/vehicles", "/api/batteries", "/api/controllers", "/api/docks",
        "/api/sensors", "/api/attachments", "/api/other-equipment",
        "/api/components", "/api/vehicle-registrations", "/api/equipment-checkouts",
    ],
    "flights": [
        "/api/flights", "/api/telemetry", "/api/flight-plans",
        "/api/mission-logs", "/api/training-logs",
    ],
    "pilots": [
        "/api/pilots", "/api/certification-types", "/api/pilot-certifications",
        "/api/pilot-equipment-quals", "/api/certifications", "/api/currency",
    ],
    "maintenance": ["/api/maintenance"],
    "operations": [
        "/api/calendar", "/api/checklists", "/api/incidents", "/api/alerts",
        "/api/geofences", "/api/weather", "/api/adsb", "/api/search",
    ],
    "documents": ["/api/documents", "/api/folders", "/api/photos", "/api/media"],
    "reports": ["/api/reports", "/api/export", "/api/dashboard", "/api/compliance"],
}

READ_METHODS = {"GET", "HEAD", "OPTIONS"}

# last_used_at write throttle so hot polling doesn't write on every request.
_LAST_USED_MIN_INTERVAL = timedelta(seconds=60)


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def token_scopes(token: ApiToken) -> list[str] | None:
    """Parse the stored scopes JSON. None means all areas."""
    if not token.scopes:
        return None
    try:
        return json.loads(token.scopes)
    except ValueError:
        return []


def _path_allowed(path: str, scopes: list[str] | None) -> bool:
    areas = SCOPE_PREFIXES.keys() if scopes is None else scopes
    for area in areas:
        for prefix in SCOPE_PREFIXES.get(area, []):
            if path == prefix or path.startswith(prefix + "/"):
                return True
    return False


def authenticate_api_token(db: Session, raw: str, method: str, path: str) -> User:
    """Resolve an API token to its owning user, enforcing scopes.

    Raises 401 for unknown/revoked tokens and 403 for out-of-scope or
    write-with-read-only requests.
    """
    token = db.query(ApiToken).filter(ApiToken.token_hash == hash_token(raw)).first()
    if not token or token.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if token.read_only and method.upper() not in READ_METHODS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token is read-only")
    if not _path_allowed(path, token_scopes(token)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token scope does not allow this endpoint")
    user = db.query(User).filter(User.id == token.user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token owner is inactive")
    now = datetime.utcnow()
    if token.last_used_at is None or now - token.last_used_at > _LAST_USED_MIN_INTERVAL:
        token.last_used_at = now
        db.commit()
    return user
