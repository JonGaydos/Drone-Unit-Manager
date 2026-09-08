"""Forward-geocoding endpoint backed by Nominatim.

Lets an admin resolve a typed address to coordinates for the organization
default location. Mirrors the HTTP pattern used by
``services/sync_manager._reverse_geocode`` (httpx, DroneUnitManager User-Agent,
short timeout).
"""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.deps import CurrentUser
from app.logsafe import for_log
from app.responses import responses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/geocode", tags=["geocode"])

_NOMINATIM = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": "DroneUnitManager/1.0"}


def _nominatim(endpoint: str, params: dict, context: str):
    """GET a Nominatim endpoint and return the parsed JSON.

    Raises 502 on any upstream/network error, logging ``context`` (already
    log-sanitized by the caller). Shared by forward and reverse geocoding.
    """
    try:
        resp = httpx.get(f"{_NOMINATIM}/{endpoint}", params=params, headers=_HEADERS, timeout=8.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("%s failed for %s: %s", endpoint, context, e)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")


@router.get("", responses=responses(404, 502))
def geocode(q: Annotated[str, Query(min_length=2, max_length=200)], user: CurrentUser):
    """Forward-geocode an address via Nominatim and return the best match.

    Returns ``{lat, lon, display_name}`` for the first result. Raises 404 when
    there is no match and 502 on any upstream/network error.
    """
    results = _nominatim(
        "search",
        {"q": q, "format": "jsonv2", "limit": 1, "addressdetails": 0},
        for_log(q),
    )
    if not results:
        raise HTTPException(status_code=404, detail="No match for that address")
    r = results[0]
    try:
        lat = float(r["lat"])
        lon = float(r["lon"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="No usable coordinates for that address")
    return {"lat": lat, "lon": lon, "display_name": r.get("display_name", q)}


@router.get("/reverse", responses=responses(404, 502))
def reverse_geocode(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    user: CurrentUser,
):
    """Reverse-geocode coordinates to a display address via Nominatim.

    Returns ``{lat, lon, display_name}``. Raises 404 when there is no address
    for the point and 502 on any upstream/network error. Lets the weather
    location picker fill the address field when the user clicks the map.
    """
    result = _nominatim(
        "reverse",
        {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 0},
        f"{lat},{lon}",
    )
    name = result.get("display_name") if isinstance(result, dict) else None
    if not name:
        raise HTTPException(status_code=404, detail="No address for those coordinates")
    return {"lat": lat, "lon": lon, "display_name": name}
