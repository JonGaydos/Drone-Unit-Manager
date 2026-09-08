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


@router.get("", responses=responses(404, 502))
def geocode(q: Annotated[str, Query(min_length=2, max_length=200)], user: CurrentUser):
    """Forward-geocode an address via Nominatim and return the best match.

    Returns ``{lat, lon, display_name}`` for the first result. Raises 404 when
    there is no match and 502 on any upstream/network error.
    """
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "jsonv2", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": "DroneUnitManager/1.0"},
            timeout=8.0,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as e:
        logger.warning("Geocode lookup failed for %s: %s", for_log(q), e)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")
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
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 0},
            headers={"User-Agent": "DroneUnitManager/1.0"},
            timeout=8.0,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        logger.warning("Reverse geocode failed for %s,%s: %s", lat, lon, e)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")
    name = result.get("display_name") if isinstance(result, dict) else None
    if not name:
        raise HTTPException(status_code=404, detail="No address for those coordinates")
    return {"lat": lat, "lon": lon, "display_name": name}
