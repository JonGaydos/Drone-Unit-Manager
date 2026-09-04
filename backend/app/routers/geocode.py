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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/geocode", tags=["geocode"])


@router.get("")
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
        logger.warning("Geocode lookup failed for %r: %s", q, e)
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
