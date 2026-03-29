"""ADS-B aircraft tracking proxy endpoint.

Proxies requests to the airplanes.live API with server-side caching
to respect rate limits and avoid CORS issues.
"""

import logging
import time
import threading
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/adsb", tags=["adsb"])

# In-memory cache to respect airplanes.live 1 req/sec rate limit
_cache = {"data": None, "timestamp": 0, "key": ""}
_cache_lock = threading.Lock()
_CACHE_TTL = 5  # seconds


@router.get("/nearby")
def get_nearby_aircraft(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    radius_nm: int = Query(30, ge=5, le=250, description="Search radius in nautical miles"),
    _user=Depends(get_current_user),
):
    """Fetch nearby aircraft positions from the airplanes.live ADS-B API.

    Results are cached for 5 seconds to respect the API's 1 req/sec rate limit.
    Aircraft without position data are filtered out.

    Args:
        lat: Center latitude for the search area.
        lon: Center longitude for the search area.
        radius_nm: Search radius in nautical miles (5-250).

    Returns:
        Dict with aircraft list and metadata (count, cache_age).
    """
    global _cache

    cache_key = f"{lat:.2f},{lon:.2f},{radius_nm}"
    now = time.time()

    # Return cached data if fresh enough (thread-safe read)
    with _cache_lock:
        if _cache["key"] == cache_key and (now - _cache["timestamp"]) < _CACHE_TTL:
            return {
                "aircraft": _cache["data"],
                "count": len(_cache["data"]),
                "cached": True,
                "cache_age_seconds": round(now - _cache["timestamp"], 1),
            }

    # Fetch from airplanes.live API
    url = f"https://api.airplanes.live/v2/point/{lat}/{lon}/{radius_nm}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "ADS-B data source timed out")
    except httpx.HTTPStatusError as e:
        logger.warning("ADS-B API error: %s", e)
        raise HTTPException(502, "ADS-B data source returned an error")
    except Exception as e:
        logger.error("ADS-B fetch failed: %s", e)
        raise HTTPException(502, "Failed to fetch ADS-B data")

    # Parse and clean aircraft data
    raw_aircraft = data.get("ac", [])
    aircraft = []
    for ac in raw_aircraft:
        # Skip entries without position
        if ac.get("lat") is None or ac.get("lon") is None:
            continue

        aircraft.append({
            "icao": ac.get("hex", "").upper(),
            "callsign": (ac.get("flight") or "").strip(),
            "registration": ac.get("r", ""),
            "aircraft_type": ac.get("t", ""),
            "category": ac.get("category", ""),
            "lat": ac["lat"],
            "lon": ac["lon"],
            "alt_baro": ac.get("alt_baro"),
            "alt_geom": ac.get("alt_geom"),
            "gs": ac.get("gs"),  # Ground speed in knots
            "track": ac.get("track"),  # Heading in degrees
            "baro_rate": ac.get("baro_rate"),  # Vertical rate ft/min
            "squawk": ac.get("squawk", ""),
            "emergency": ac.get("emergency", "none"),
            "seen": ac.get("seen", 0),  # Seconds since last message
        })

    # Update cache (thread-safe write)
    with _cache_lock:
        _cache = {"data": aircraft, "timestamp": now, "key": cache_key}

    return {
        "aircraft": aircraft,
        "count": len(aircraft),
        "cached": False,
        "cache_age_seconds": 0,
    }
