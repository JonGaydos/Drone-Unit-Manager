"""Skydio Cloud API provider implementation."""

import logging
import time
from datetime import datetime

import httpx

from app.constants import UTC_OFFSET
from app.integrations.base import DroneProvider, ProviderCredentials
from app.integrations.registry import register_provider

logger = logging.getLogger(__name__)

BASE_URL = "https://api.skydio.com/api/v0"
TELEMETRY_BASE = "https://api.skydio.com/api/v1"
MAX_RETRIES = 3


def _log_provider_error(action: str, exc: Exception) -> None:
    """Log a Skydio provider failure at the right volume.

    An error status the Skydio API returned (HTTPStatusError, e.g. a 403 for a
    scope the token lacks or a 500 on their side) is expected and recovered from,
    so it logs a single warning line. Anything else (a bug here, a JSON/parse
    failure) keeps its full traceback so real problems stay debuggable.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        logger.warning("Could not %s: Skydio API returned HTTP %s for %s",
                       action, exc.response.status_code, exc.request.url)
    else:
        logger.error("Failed to %s", action, exc_info=exc)


def _to_str(val):
    """Convert API values to strings for DB storage. Handles dicts, lists, None."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # Extract the most useful field from a dict (serial, name, type)
        for key in ("serial", "serial_number", "name", "type", "sensor_package_serial"):
            if key in val:
                return str(val[key])
        return str(val)
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def _clean_serial(val):
    """Serial string with Skydio's leading-dash artifact stripped."""
    s = _to_str(val)
    return s.lstrip("-") if s else s


def _first_of(d: dict, *keys):
    """Return the first truthy value from dict for the given keys (matches `or` chain semantics)."""
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def _map_raw_flight(f: dict) -> dict:
    """Map a raw Skydio API flight dict to our standard flight dict format."""
    takeoff_time = None
    landing_time = None
    flight_date = None

    takeoff_str = _first_of(f, "takeoff_time", "takeoff", "start_time")
    landing_str = _first_of(f, "landing_time", "landing", "end_time")

    if takeoff_str:
        try:
            takeoff_time = datetime.fromisoformat(takeoff_str.replace("Z", UTC_OFFSET))
            flight_date = takeoff_time.date().isoformat()
        except (ValueError, AttributeError):
            pass

    if landing_str:
        try:
            landing_time = datetime.fromisoformat(landing_str.replace("Z", UTC_OFFSET))
        except (ValueError, AttributeError):
            pass

    duration = _first_of(f, "duration_seconds", "duration")
    if duration is None and takeoff_time and landing_time:
        duration = int((landing_time - takeoff_time).total_seconds())

    return {
        "external_id": _first_of(f, "flight_id", "uuid", "id"),
        "api_provider": "skydio",
        "date": flight_date or f.get("date"),
        "takeoff_time": takeoff_time,
        "landing_time": landing_time,
        "duration_seconds": duration,
        "takeoff_lat": _first_of(f, "takeoff_latitude", "takeoff_lat"),
        "takeoff_lon": _first_of(f, "takeoff_longitude", "takeoff_lon"),
        "landing_lat": _first_of(f, "landing_latitude", "landing_lat"),
        "landing_lon": _first_of(f, "landing_longitude", "landing_lon"),
        "takeoff_address": _first_of(f, "takeoff_address", "location"),
        "pilot_name": _first_of(f, "pilot_name", "operator_name"),
        "vehicle_serial": _first_of(f, "vehicle_serial", "serial_number"),
        "max_altitude_m": _first_of(f, "max_altitude_m", "max_altitude"),
        "max_speed_mps": _first_of(f, "max_speed_mps", "max_speed"),
        "distance_m": _first_of(f, "distance_m", "total_distance"),
        "battery_serial": _clean_serial(_first_of(f, "battery_serial", "battery")),
        "sensor_package": _to_str(f.get("sensor_package")),
        "attachment_top": _to_str(f.get("attachment_top")),
        "attachment_bottom": _to_str(f.get("attachment_bottom")),
        "attachment_left": _to_str(f.get("attachment_left")),
        "attachment_right": _to_str(f.get("attachment_right")),
        "carrier": _to_str(_first_of(f, "carrier", "carriers")),
    }


def _first_list_in_dict(d: dict) -> list | None:
    """The first telemetry list under a known key, or the first list nested one
    level deeper under such a key. None if nothing list-shaped is found."""
    for key in ("flight_telemetry", "telemetry", "points", "data"):
        val = d.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            for subval in val.values():
                if isinstance(subval, list):
                    return subval
    return None


def _unwrap_telemetry_response(body) -> list:
    """Unwrap nested Skydio telemetry response to get a flat list of point dicts."""
    raw = body
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        raw = raw["data"]
    if isinstance(raw, dict):
        found = _first_list_in_dict(raw)
        if found is not None:
            return found
    if isinstance(raw, list):
        return raw
    return []


def _telemetry_point_derived(p: dict, takeoff_gps_alt: float | None):
    """Compute (battery %, altitude AGL, horizontal speed) for a raw point.

    Battery is normalized to a percentage (Skydio sends 0-1 or 0-100); altitude
    prefers height_above_takeoff, else derives AGL from gps_altitude minus the
    takeoff ground level; speed is the horizontal magnitude of the velocity
    vector. Any of the three may be None when the inputs are absent.
    """
    import math

    battery = p.get("battery_percentage")
    if battery is not None and battery <= 1.0:
        battery = round(battery * 100, 1)

    alt_hat = p.get("height_above_takeoff")
    if alt_hat is not None:
        alt = alt_hat
    elif p.get("gps_altitude") is not None and takeoff_gps_alt is not None:
        alt = p["gps_altitude"] - takeoff_gps_alt
    else:
        alt = None

    velocity = p.get("gps_velocity")
    speed = None
    if isinstance(velocity, list) and len(velocity) >= 2:
        speed = round(math.sqrt(sum(v**2 for v in velocity[:3])), 2)

    return battery, alt, speed


def _map_telemetry_point(p: dict, takeoff_gps_alt: float | None) -> dict | None:
    """Map a raw Skydio telemetry point to our standard format."""
    if not isinstance(p, dict):
        return None

    battery, alt, speed = _telemetry_point_derived(p, takeoff_gps_alt)

    return {
        "timestamp_ms": p.get("timestamp_ms") or p.get("timestamp"),
        "lat": p.get("gps_latitude") or p.get("lat"),
        "lon": p.get("gps_longitude") or p.get("lon"),
        "altitude_m": round(alt, 2) if alt is not None else None,
        "speed_mps": speed,
        "battery_pct": battery,
        "battery_voltage": p.get("battery_voltage"),
        "heading_deg": p.get("heading_deg") or p.get("heading"),
        "pitch_deg": p.get("pitch_deg") or p.get("pitch"),
        "roll_deg": p.get("roll_deg") or p.get("roll"),
        "satellites": p.get("gps_num_satellites_used") or p.get("satellites"),
    }


def _extract_oldest_date(raw: list[dict]) -> str | None:
    """Extract the oldest date string from a batch of raw flight dicts."""
    dates = []
    for f in raw:
        dt = f.get("takeoff_time") or f.get("start_time") or f.get("created_at")
        if dt:
            dates.append(dt)
    if not dates:
        return None
    oldest = min(dates)
    return oldest[:10] if len(oldest) > 10 else oldest


class SkydioProvider(DroneProvider):
    PROVIDER_NAME = "skydio"

    def _headers(self, creds: ProviderCredentials) -> dict:
        return {
            "Authorization": f"ApiToken {creds.api_token}",
            "X-Api-Token-Id": creds.token_id,
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        url: str,
        creds: ProviderCredentials,
        params: dict | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        """Make an HTTP request with rate-limit retry logic."""
        headers = self._headers(creds)
        for attempt in range(MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(method, url, headers=headers, params=params)

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "5"))
                    if attempt < MAX_RETRIES:
                        logger.warning(
                            "Rate limited by Skydio API, retrying after %.1fs (attempt %d/%d)",
                            retry_after, attempt + 1, MAX_RETRIES,
                        )
                        time.sleep(retry_after)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("HTTP error on attempt %d: %s", attempt + 1, exc)
                    time.sleep(2)
                    continue
                raise

        # Should not reach here, but just in case
        raise RuntimeError("Max retries exceeded for Skydio API request")

    @staticmethod
    def _extract_items_from_body(body: dict) -> list | None:
        """Extract item list from a Skydio API response dict. Returns None if no list found."""
        items = body.get("data") or body.get("results") or []

        if isinstance(items, dict):
            for key, val in items.items():
                if isinstance(val, list):
                    logger.info("  Found list under 'data.%s' with %d items", key, len(val))
                    return val
            logger.warning("Nested dict in 'data' but no list found. Keys: %s", list(items.keys()))
            return None

        if not isinstance(items, list):
            logger.warning("Expected list but got %s", type(items).__name__)
            return None

        return items

    @staticmethod
    def _advance_pagination(body: dict, params: dict, all_data: list) -> tuple[str | None, dict]:
        """Determine next page params. Returns (new_url_or_None, updated_params)."""
        next_cursor = body.get("next") or body.get("next_cursor")
        if next_cursor:
            if isinstance(next_cursor, str) and next_cursor.startswith("http"):
                return next_cursor, {}
            params["cursor"] = next_cursor
            return None, params

        if body.get("has_more"):
            params["offset"] = len(all_data)
            return None, params

        if body.get("page") is not None and body.get("total", 0) > len(all_data):
            params["page"] = body["page"] + 1
            return None, params

        return "STOP", params

    @staticmethod
    def _log_page(url: str, page: int, resp: httpx.Response, body) -> None:
        """Log one page's shape and any pagination fields (diagnostic only)."""
        shape = list(body.keys()) if isinstance(body, dict) else f"list[{len(body)}]"
        logger.info("Paginate %s (page %d): status=%d, type=%s, keys=%s",
                    url.split("/")[-1], page, resp.status_code, type(body).__name__, shape)
        if isinstance(body, dict):
            for pkey in ("next", "next_cursor", "cursor", "has_more", "total",
                         "count", "page", "per_page", "offset", "limit"):
                if pkey in body:
                    logger.info("  Pagination field '%s': %s", pkey, body[pkey])

    def _consume_page(self, body, params: dict, all_data: list) -> tuple[dict, str | None, bool]:
        """Fold one page body into all_data and report the next step.

        Returns (params, next_url_or_None, stop). A bare list is the whole
        result; a non-dict body is unusable; an empty item set ends paging.
        Otherwise the items are appended and the next page computed -- the offset
        math runs after the extend, exactly as the original loop did.
        """
        if isinstance(body, list):
            all_data.extend(body)
            return params, None, True
        if not isinstance(body, dict):
            return params, None, True
        items = self._extract_items_from_body(body)
        if not items:
            return params, None, True
        all_data.extend(items)
        logger.info("  Got %d items this page, %d total", len(items), len(all_data))
        new_url, params = self._advance_pagination(body, params, all_data)
        if new_url == "STOP":
            return params, None, True
        return params, new_url, False

    def _paginate(
        self,
        url: str,
        creds: ProviderCredentials,
        params: dict | None = None,
        default_per_page: int | None = 200,
    ) -> list[dict]:
        """Fetch all pages from a paginated Skydio endpoint (100-page safety cap)."""
        all_data = []
        params = dict(params or {})
        if default_per_page is not None:
            params.setdefault("per_page", default_per_page)

        for page in range(1, 101):
            resp = self._request("GET", url, creds, params=params)
            body = resp.json()
            self._log_page(url, page, resp, body)
            params, new_url, stop = self._consume_page(body, params, all_data)
            if stop:
                break
            if new_url is not None:
                url = new_url
        else:
            logger.warning("Pagination safety limit reached (100 pages), stopping")

        logger.info("Paginate complete: %d total items", len(all_data))
        return all_data

    # ---- Provider interface implementation ----

    def validate_credentials(self, creds: ProviderCredentials) -> bool:
        """Validate credentials by calling the whoami endpoint."""
        try:
            resp = self._request("GET", f"{BASE_URL}/whoami", creds)
            data = resp.json()
            logger.info("Skydio credentials valid. User: %s", data)
            return True
        except Exception as exc:
            _log_provider_error("validate Skydio credentials", exc)
            return False

    def get_user_info(self, creds: ProviderCredentials) -> dict:
        """Get the authenticated user info (used for test_connection)."""
        try:
            resp = self._request("GET", f"{BASE_URL}/whoami", creds)
            return resp.json()
        except Exception as exc:
            _log_provider_error("get Skydio user info", exc)
            return {}

    def sync_vehicles(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch all vehicles from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/vehicles", creds)
            logger.info("Skydio vehicles raw response: %d items", len(raw))
            if raw:
                logger.info("First vehicle keys: %s", list(raw[0].keys()) if raw else "empty")
            vehicles = []
            for v in raw:
                vehicles.append({
                    "serial_number": v.get("serial_number", v.get("vehicle_serial", "")),
                    "manufacturer": "Skydio",
                    "model": v.get("model", v.get("vehicle_type", "Unknown")),
                    "provider_serial": v.get("serial_number", v.get("vehicle_serial", "")),
                    "api_provider": "skydio",
                    "nickname": v.get("name") or v.get("nickname"),
                })
            logger.info("Fetched %d vehicles from Skydio", len(vehicles))
            return vehicles
        except Exception as exc:
            _log_provider_error("sync Skydio vehicles", exc)
            return []

    def sync_flights(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        """Fetch flights from Skydio Cloud."""
        try:
            params = {}
            if since:
                params["date_from"] = since[:10] if len(since) > 10 else since

            raw = self._paginate(f"{BASE_URL}/flights", creds, params=params)
            if raw:
                logger.info("First flight raw keys: %s", list(raw[0].keys()))
                logger.info("First flight raw data: %s", {k: raw[0][k] for k in list(raw[0].keys())[:20]})

            flights = [_map_raw_flight(f) for f in raw]
            logger.info("Fetched %d flights from Skydio", len(flights))
            return flights
        except Exception as exc:
            _log_provider_error("sync Skydio flights", exc)
            return []

    @staticmethod
    def _collect_new_flights(raw: list[dict], seen_ids: set, all_raw: list) -> int:
        """Append flights with an unseen id to all_raw; return how many were added."""
        added = 0
        for f in raw:
            fid = f.get("flight_id") or f.get("uuid") or f.get("id")
            if fid and fid not in seen_ids:
                seen_ids.add(fid)
                all_raw.append(f)
                added += 1
        return added

    def sync_flights_deep(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch ALL historical flights by paging backwards through date windows."""
        all_raw = []
        date_to = None
        seen_ids = set()

        for batch in range(1, 51):
            params = {"per_page": 200}
            if date_to:
                params["date_to"] = date_to

            logger.info("Deep sync batch %d (date_to=%s)", batch, date_to)
            raw = self._paginate(f"{BASE_URL}/flights", creds, params=params)
            if not raw:
                logger.info("Deep sync: empty batch, stopping")
                break

            new_in_batch = self._collect_new_flights(raw, seen_ids, all_raw)
            logger.info("Deep sync batch %d: %d raw, %d new, %d total unique",
                        batch, len(raw), new_in_batch, len(all_raw))
            if new_in_batch == 0:
                logger.info("Deep sync: no new flights in batch, stopping")
                break

            # Oldest takeoff time in this batch sets the next backward window.
            next_date_to = _extract_oldest_date(raw)
            if next_date_to is None:
                logger.info("Deep sync: no dates found in batch, stopping")
                break
            if next_date_to == date_to:
                logger.info("Deep sync: date_to unchanged (%s), stopping", date_to)
                break
            date_to = next_date_to
        else:
            logger.warning("Deep sync safety limit reached: 50 batches")

        logger.info("Deep sync complete: %d total unique flights", len(all_raw))
        return [_map_raw_flight(f) for f in all_raw]

    def sync_batteries(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch batteries from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/batteries", creds)
            batteries = []
            for b in raw:
                # Skydio's `battery_serial` carries a leading-dash artifact
                # (e.g. "-k01-231117-1-00061"); `battery_name` is the clean
                # form. Store the clean serial, keep the raw one for API
                # correlation.
                raw_serial = b.get("battery_serial") or ""
                serial = b.get("battery_name") or raw_serial.lstrip("-")
                batteries.append({
                    "serial_number": serial,
                    "manufacturer": "Skydio",
                    "model": b.get("model") or b.get("battery_type"),
                    "vehicle_model": b.get("vehicle_model"),
                    "cycle_count": b.get("cycles", b.get("cycle_count", 0)),
                    "health_pct": b.get("health_pct") or b.get("state_of_health"),
                    "skydio_battery_serial": raw_serial or serial,
                    "api_provider": "skydio",
                })
            logger.info("Fetched %d batteries from Skydio", len(batteries))
            return batteries
        except Exception as exc:
            _log_provider_error("sync Skydio batteries", exc)
            return []

    def sync_controllers(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch controllers from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/controllers", creds)
            controllers = []
            for c in raw:
                controllers.append({
                    "serial_number": c.get("serial_number", c.get("controller_serial", "")),
                    "manufacturer": "Skydio",
                    "model": c.get("model") or c.get("controller_type"),
                    "skydio_controller_serial": c.get("serial_number", c.get("controller_serial", "")),
                    "api_provider": "skydio",
                })
            logger.info("Fetched %d controllers from Skydio", len(controllers))
            return controllers
        except Exception as exc:
            _log_provider_error("sync Skydio controllers", exc)
            return []

    def get_flight_detail(self, creds: ProviderCredentials, flight_id: str) -> dict | None:
        """Fetch full details for a single flight by ID."""
        try:
            resp = self._request("GET", f"{BASE_URL}/flight/{flight_id}", creds, timeout=15)
            body = resp.json()

            if not isinstance(body, dict):
                return None

            # Unwrap nested response: {"data": {"flight": {...}}} or {"flight": {...}} or {"data": {...}}
            flight = body
            if "data" in flight and isinstance(flight["data"], dict):
                flight = flight["data"]
            if "flight" in flight and isinstance(flight["flight"], dict):
                flight = flight["flight"]

            logger.info("Flight detail for %s: %d keys: %s", flight_id, len(flight.keys()), list(flight.keys()))
            return flight
        except Exception as exc:
            _log_provider_error(f"get flight detail for {flight_id}", exc)
            return None

    def get_flight_telemetry(self, creds: ProviderCredentials, flight_id: str) -> list[dict]:
        """Fetch telemetry data for a specific flight."""
        try:
            resp = self._request(
                "GET",
                f"{TELEMETRY_BASE}/flight/{flight_id}/telemetry",
                creds,
                timeout=60.0,
            )
            body = resp.json()

            raw = _unwrap_telemetry_response(body)
            if not raw:
                return []

            # Determine takeoff altitude (ground level) from the first point's gps_altitude
            takeoff_gps_alt = None
            for p in raw:
                if isinstance(p, dict) and p.get("gps_altitude") is not None:
                    takeoff_gps_alt = p["gps_altitude"]
                    break

            points = []
            for p in raw:
                mapped = _map_telemetry_point(p, takeoff_gps_alt)
                if mapped:
                    points.append(mapped)

            logger.info("Fetched %d telemetry points for flight %s", len(points), flight_id)
            return points
        except Exception as exc:
            _log_provider_error(f"fetch telemetry for flight {flight_id}", exc)
            return []

    def sync_media(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        """Fetch media files from Skydio Cloud."""
        try:
            # Note: Skydio media endpoint returns 400 with per_page, so skip it
            raw = self._paginate(f"{BASE_URL}/media/files", creds, default_per_page=None)
            media = []
            for m in raw:
                captured_time = None
                captured_str = m.get("captured_time") or m.get("created_at") or m.get("timestamp")
                if captured_str:
                    try:
                        captured_time = datetime.fromisoformat(captured_str.replace("Z", UTC_OFFSET))
                    except (ValueError, AttributeError):
                        pass

                media.append({
                    "external_uuid": m.get("uuid") or m.get("id") or m.get("file_id"),
                    "filename": m.get("filename") or m.get("name", ""),
                    "kind": m.get("kind") or m.get("type") or m.get("media_type", "photo"),
                    "captured_time": captured_time,
                    "size_bytes": m.get("size_bytes") or m.get("size"),
                    "download_url": m.get("download_url") or m.get("url"),
                    "api_provider": "skydio",
                    "flight_external_id": m.get("flight_id") or m.get("flight_uuid"),
                })

            logger.info("Fetched %d media files from Skydio", len(media))
            return media
        except Exception as exc:
            _log_provider_error("sync Skydio media", exc)
            return []

    def sync_docks(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch docks from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/docks", creds)
            docks = []
            for d in raw:
                docks.append({
                    "serial_number": d.get("serial_number", d.get("dock_serial", "")),
                    "name": d.get("name"),
                    "location_name": d.get("location_name") or d.get("location"),
                    "lat": d.get("lat") or d.get("latitude"),
                    "lon": d.get("lon") or d.get("longitude"),
                    "skydio_dock_serial": d.get("serial_number", d.get("dock_serial", "")),
                    "api_provider": "skydio",
                })
            logger.info("Fetched %d docks from Skydio", len(docks))
            return docks
        except Exception as exc:
            _log_provider_error("sync Skydio docks", exc)
            return []

    def sync_sensor_packages(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch sensor packages from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/sensor_packages", creds)
            sensors = []
            for s in raw:
                sensors.append({
                    "serial_number": s.get("serial_number", ""),
                    "name": s.get("name"),
                    "type": s.get("type") or s.get("sensor_type"),
                    "manufacturer": s.get("manufacturer", "Skydio"),
                    "model": s.get("model"),
                    "skydio_serial": s.get("serial_number", ""),
                    "api_provider": "skydio",
                })
            logger.info("Fetched %d sensor packages from Skydio", len(sensors))
            return sensors
        except Exception as exc:
            _log_provider_error("sync Skydio sensor packages", exc)
            return []

    def sync_attachments(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch attachments from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/attachments", creds)
            attachments = []
            for a in raw:
                attachments.append({
                    "serial_number": a.get("serial_number", ""),
                    "name": a.get("name"),
                    "type": a.get("type") or a.get("attachment_type"),
                    "manufacturer": a.get("manufacturer", "Skydio"),
                    "model": a.get("model"),
                    "skydio_serial": a.get("serial_number", ""),
                    "api_provider": "skydio",
                })
            logger.info("Fetched %d attachments from Skydio", len(attachments))
            return attachments
        except Exception as exc:
            _log_provider_error("sync Skydio attachments", exc)
            return []

    def sync_users(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch users from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/users", creds)
            users = []
            for u in raw:
                name = u.get("name") or ""
                email = u.get("email") or ""
                uuid = u.get("uuid") or u.get("id") or ""
                users.append({
                    "name": name,
                    "email": email,
                    "uuid": str(uuid),
                })
            logger.info("Fetched %d users from Skydio", len(users))
            return users
        except Exception as exc:
            _log_provider_error("sync Skydio users", exc)
            return []


# Register the provider with the registry
register_provider(SkydioProvider)
