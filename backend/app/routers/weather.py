import httpx
import json
import logging
from math import radians, sin, cos, sqrt, atan2
from typing import Annotated
from fastapi import APIRouter, Query
from sqlalchemy.orm import Session
from app.deps import DBSession, CurrentUser
from app.models.setting import Setting
from app.responses import responses

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["weather"])

# METAR station list (top US stations) — we'll find nearest dynamically
METAR_URL = "https://aviationweather.gov/api/data/metar"
TAF_URL = "https://aviationweather.gov/api/data/taf"
STATION_URL = "https://aviationweather.gov/api/data/stationinfo"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def _haversine(lat1, lon1, lat2, lon2):
    R = 3959  # miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def _get_thresholds(db: Session):
    """Read custom weather thresholds from DB settings, merged with defaults."""
    setting = db.query(Setting).filter(Setting.key == "weather_thresholds").first()
    if setting and setting.value:
        try:
            custom = json.loads(setting.value)
            return {**DEFAULT_THRESHOLDS, **custom}
        except Exception:
            pass
    return DEFAULT_THRESHOLDS


def _fetch_metar_taf(lat: float, lon: float) -> dict:
    """Fetch nearest METAR station, current METAR, and TAF forecast."""
    result = {"metar": None, "taf": None, "station": None}

    with httpx.Client(timeout=10) as client:
        station_resp = client.get(STATION_URL, params={
            "bbox": f"{lat-1},{lon-1},{lat+1},{lon+1}",
            "format": "json",
        })
        stations = station_resp.json() if station_resp.status_code == 200 else []

        nearest_station = None
        min_dist = float('inf')
        for s in stations:
            if isinstance(s, dict) and s.get("lat") and s.get("lon"):
                d = _haversine(lat, lon, float(s["lat"]), float(s["lon"]))
                if d < min_dist:
                    min_dist = d
                    nearest_station = s

        if not nearest_station:
            return result

        station_id = nearest_station.get("icaoId") or nearest_station.get("id", "")
        result["station"] = {
            "id": station_id,
            "name": nearest_station.get("name", ""),
            "distance_miles": round(min_dist, 1),
            "lat": nearest_station.get("lat"),
            "lon": nearest_station.get("lon"),
        }

        metar_resp = client.get(METAR_URL, params={"ids": station_id, "format": "json", "hours": 2})
        if metar_resp.status_code == 200:
            metar_data = metar_resp.json()
            if metar_data and isinstance(metar_data, list) and len(metar_data) > 0:
                m = metar_data[0]
                result["metar"] = {
                    "raw": m.get("rawOb", ""),
                    "station": station_id,
                    "temp_c": m.get("temp"),
                    "dewpoint_c": m.get("dewp"),
                    "wind_dir_deg": m.get("wdir"),
                    "wind_speed_kt": m.get("wspd"),
                    "wind_gust_kt": m.get("wgst"),
                    "visibility_miles": m.get("visib"),
                    "ceiling_ft": m.get("ceil"),
                    "flight_category": m.get("fltcat"),
                    "wx_string": m.get("wxString"),
                    "altimeter_inhg": m.get("altim"),
                    "observation_time": m.get("reportTime"),
                    "clouds": m.get("clouds", []),
                }

        taf_resp = client.get(TAF_URL, params={"ids": station_id, "format": "json"})
        if taf_resp.status_code == 200:
            taf_data = taf_resp.json()
            if taf_data and isinstance(taf_data, list) and len(taf_data) > 0:
                result["taf"] = {
                    "raw": taf_data[0].get("rawTAF", ""),
                    "station": station_id,
                    "forecasts": taf_data[0].get("fcsts", []),
                }

    return result


def _fetch_local_weather(lat: float, lon: float) -> tuple[dict | None, list | None]:
    """Fetch hyperlocal weather from Open-Meteo. Returns (local_weather, forecast)."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(OPEN_METEO_URL, params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m,cloud_cover,visibility",
            "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m,visibility,cloud_cover,weather_code",
            "forecast_hours": 12,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        })
        if resp.status_code != 200:
            return None, None

        data = resp.json()
        current = data.get("current", {})
        local_weather = {
            "temperature_f": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_mph": current.get("wind_speed_10m"),
            "wind_direction_deg": current.get("wind_direction_10m"),
            "wind_gusts_mph": current.get("wind_gusts_10m"),
            "precipitation_in": current.get("precipitation"),
            "cloud_cover_pct": current.get("cloud_cover"),
            "visibility_ft": round(current.get("visibility", 0) * 3.281) if current.get("visibility") else None,
            "weather_code": current.get("weather_code"),
        }

        forecast = None
        hourly = data.get("hourly", {})
        if hourly.get("time"):
            forecast = [{
                "time": hourly["time"][i],
                "temp_f": hourly.get("temperature_2m", [None]*12)[i],
                "precip_prob": hourly.get("precipitation_probability", [None]*12)[i],
                "wind_mph": hourly.get("wind_speed_10m", [None]*12)[i],
                "gusts_mph": hourly.get("wind_gusts_10m", [None]*12)[i],
                "visibility_ft": round((hourly.get("visibility", [0]*12)[i] or 0) * 3.281),
                "cloud_cover": hourly.get("cloud_cover", [None]*12)[i],
            } for i in range(min(12, len(hourly["time"])))]

        return local_weather, forecast


@router.get("/briefing")
def get_weather_briefing(
    db: DBSession,
    user: CurrentUser,
    lat: Annotated[float, Query()],
    lon: Annotated[float, Query()],
):
    """Get comprehensive weather briefing for a GPS location."""
    result = {
        "location": {"lat": lat, "lon": lon},
        "metar": None,
        "taf": None,
        "local_weather": None,
        "advisory": {"status": "unknown", "reasons": []},
        "station": None,
    }

    try:
        aviation_data = _fetch_metar_taf(lat, lon)
        result["metar"] = aviation_data["metar"]
        result["taf"] = aviation_data["taf"]
        result["station"] = aviation_data["station"]
    except Exception as exc:
        logger.warning("METAR/TAF fetch failed: %s", exc)

    try:
        local_weather, forecast = _fetch_local_weather(lat, lon)
        result["local_weather"] = local_weather
        if forecast:
            result["forecast"] = forecast
    except Exception as exc:
        logger.warning("Open-Meteo fetch failed: %s", exc)

    thresholds = _get_thresholds(db)
    result["advisory"] = _compute_advisory(result, thresholds)

    return result


@router.get("/thresholds", responses=responses(401))
def get_thresholds(db: DBSession, user: CurrentUser):
    """Return the current weather thresholds (custom + defaults merged)."""
    return _get_thresholds(db)


DEFAULT_THRESHOLDS = {
    "wind_sustained_go": 15,
    "wind_sustained_caution": 25,
    "wind_gusts_go": 20,
    "wind_gusts_caution": 30,
    "visibility_go": 3,  # miles
    "visibility_caution": 1,
    "ceiling_go": 500,  # feet AGL
    "ceiling_caution": 200,
    "temp_low_go": 32,  # F
    "temp_low_caution": 20,
    "temp_high_go": 100,
    "precip_caution": 0.01,  # inches
}

def _escalate_status(current: str, new_level: str) -> str:
    """Escalate advisory status: go -> caution -> no_go (never downgrade)."""
    severity = {"go": 0, "caution": 1, "no_go": 2}
    return new_level if severity.get(new_level, 0) > severity.get(current, 0) else current


def _check_threshold_pair(value, go_limit, caution_limit, status, reasons,
                          no_go_msg: str, caution_msg: str) -> str:
    """Check a value against go/caution thresholds. Returns updated status."""
    if value is None:
        return status
    if value > caution_limit:
        reasons.append(no_go_msg)
        return "no_go"
    if value > go_limit:
        reasons.append(caution_msg)
        return _escalate_status(status, "caution")
    return status


def _check_threshold_pair_below(value, go_limit, caution_limit, status, reasons,
                                no_go_msg: str, caution_msg: str) -> str:
    """Check a value against go/caution thresholds where LOWER is worse. Returns updated status."""
    if value is None:
        return status
    if value < caution_limit:
        reasons.append(no_go_msg)
        return "no_go"
    if value < go_limit:
        reasons.append(caution_msg)
        return _escalate_status(status, "caution")
    return status


def _compute_advisory(data, thresholds=None):
    reasons = []
    status = "go"

    lw = data.get("local_weather") or {}
    metar = data.get("metar") or {}
    t = thresholds or DEFAULT_THRESHOLDS

    wind = lw.get("wind_speed_mph") or (metar.get("wind_speed_kt", 0) or 0) * 1.151
    gusts = lw.get("wind_gusts_mph") or (metar.get("wind_gust_kt", 0) or 0) * 1.151

    status = _check_threshold_pair(
        wind, t["wind_sustained_go"], t["wind_sustained_caution"], status, reasons,
        f"Wind {wind:.0f} mph exceeds {t['wind_sustained_caution']} mph limit",
        f"Wind {wind:.0f} mph — exercise caution (limit: {t['wind_sustained_caution']} mph)")

    status = _check_threshold_pair(
        gusts, t["wind_gusts_go"], t["wind_gusts_caution"], status, reasons,
        f"Gusts {gusts:.0f} mph exceed {t['wind_gusts_caution']} mph limit",
        f"Gusts {gusts:.0f} mph — exercise caution")

    vis = metar.get("visibility_miles")
    status = _check_threshold_pair_below(
        vis, t["visibility_go"], t["visibility_caution"], status, reasons,
        f"Visibility {vis} miles — below minimum",
        f"Visibility {vis} miles — reduced")

    ceil = metar.get("ceiling_ft")
    status = _check_threshold_pair_below(
        ceil, t["ceiling_go"], t["ceiling_caution"], status, reasons,
        f"Ceiling {ceil} ft AGL — below minimum",
        f"Ceiling {ceil} ft AGL — low")

    temp = lw.get("temperature_f")
    if temp is not None:
        if temp < t["temp_low_caution"]:
            status = "no_go"
            reasons.append(f"Temperature {temp:.0f}\u00b0F — too cold for safe operations")
        elif temp < t["temp_low_go"]:
            status = _escalate_status(status, "caution")
            reasons.append(f"Temperature {temp:.0f}\u00b0F — cold conditions")
        elif temp > t["temp_high_go"]:
            status = _escalate_status(status, "caution")
            reasons.append(f"Temperature {temp:.0f}\u00b0F — hot conditions")

    precip = lw.get("precipitation_in", 0) or 0
    if precip > t["precip_caution"]:
        status = _escalate_status(status, "caution")
        reasons.append(f"Active precipitation: {precip:.2f} in")

    fltcat = metar.get("flight_category")
    if fltcat in ("IFR", "LIFR"):
        status = "no_go"
        reasons.append(f"Flight category: {fltcat}")
    elif fltcat == "MVFR":
        status = _escalate_status(status, "caution")
        reasons.append(f"Flight category: {fltcat}")

    if not reasons:
        reasons.append("All conditions within safe operating limits")

    return {"status": status, "reasons": reasons}
