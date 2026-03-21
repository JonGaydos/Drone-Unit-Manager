"""Skydio Cloud API provider implementation."""

import logging
import time
from datetime import datetime

import httpx

from app.integrations.base import DroneProvider, ProviderCredentials
from app.integrations.registry import register_provider

logger = logging.getLogger(__name__)

BASE_URL = "https://api.skydio.com/api/v0"
TELEMETRY_BASE = "https://api.skydio.com/api/v1"
MAX_RETRIES = 3


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

    def _paginate(
        self,
        url: str,
        creds: ProviderCredentials,
        params: dict | None = None,
    ) -> list[dict]:
        """Fetch all pages from a paginated Skydio endpoint."""
        all_data = []
        params = dict(params or {})
        page = 0

        while True:
            page += 1
            resp = self._request("GET", url, creds, params=params)
            body = resp.json()

            logger.info("Paginate %s (page %d): status=%d, type=%s, keys=%s",
                url.split("/")[-1], page, resp.status_code,
                type(body).__name__,
                list(body.keys()) if isinstance(body, dict) else f"list[{len(body)}]")

            # Skydio API may return data in "data", "results", or as top-level list
            if isinstance(body, list):
                all_data.extend(body)
                break
            elif isinstance(body, dict):
                items = body.get("data") or body.get("results") or []

                # Handle nested dict: {"data": {"vehicles": [...]}} or {"data": {"key": [...]}}
                if isinstance(items, dict):
                    # Try to find the list inside the nested dict
                    for key, val in items.items():
                        if isinstance(val, list):
                            logger.info("  Found list under 'data.%s' with %d items", key, len(val))
                            items = val
                            break
                    else:
                        logger.warning("Nested dict in 'data' but no list found. Keys: %s", list(items.keys()))
                        break

                if not isinstance(items, list):
                    logger.warning("Expected list but got %s", type(items).__name__)
                    break

                all_data.extend(items)
                logger.info("  Got %d items this page, %d total", len(items), len(all_data))

                # Check for next page cursor/URL
                next_cursor = body.get("next") or body.get("next_cursor")
                if not next_cursor:
                    break

                # If next is a full URL, use it directly
                if isinstance(next_cursor, str) and next_cursor.startswith("http"):
                    url = next_cursor
                    params = {}
                else:
                    params["cursor"] = next_cursor
            else:
                break

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
            logger.error("Skydio credential validation failed: %s", exc)
            return False

    def get_user_info(self, creds: ProviderCredentials) -> dict:
        """Get the authenticated user info (used for test_connection)."""
        try:
            resp = self._request("GET", f"{BASE_URL}/whoami", creds)
            return resp.json()
        except Exception as exc:
            logger.error("Failed to get Skydio user info: %s", exc)
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
                    "skydio_vehicle_serial": v.get("serial_number", v.get("vehicle_serial", "")),
                    "api_provider": "skydio",
                    "nickname": v.get("name") or v.get("nickname"),
                })
            logger.info("Fetched %d vehicles from Skydio", len(vehicles))
            return vehicles
        except Exception as exc:
            logger.error("Failed to sync Skydio vehicles: %s", exc, exc_info=True)
            return []

    def sync_flights(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        """Fetch flights from Skydio Cloud."""
        try:
            params = {}
            if since:
                params["date_from"] = since[:10] if len(since) > 10 else since

            raw = self._paginate(f"{BASE_URL}/flights", creds, params=params)
            flights = []
            for f in raw:
                # Parse timestamps
                takeoff_time = None
                landing_time = None
                flight_date = None

                takeoff_str = f.get("takeoff_time") or f.get("start_time")
                landing_str = f.get("landing_time") or f.get("end_time")

                if takeoff_str:
                    try:
                        takeoff_time = datetime.fromisoformat(takeoff_str.replace("Z", "+00:00"))
                        flight_date = takeoff_time.date().isoformat()
                    except (ValueError, AttributeError):
                        pass

                if landing_str:
                    try:
                        landing_time = datetime.fromisoformat(landing_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass

                duration = f.get("duration_seconds") or f.get("duration")
                if duration is None and takeoff_time and landing_time:
                    duration = int((landing_time - takeoff_time).total_seconds())

                # Extract location data
                takeoff_lat = f.get("takeoff_latitude") or f.get("takeoff_lat")
                takeoff_lon = f.get("takeoff_longitude") or f.get("takeoff_lon")
                landing_lat = f.get("landing_latitude") or f.get("landing_lat")
                landing_lon = f.get("landing_longitude") or f.get("landing_lon")

                flights.append({
                    "external_id": f.get("flight_id") or f.get("uuid") or f.get("id"),
                    "api_provider": "skydio",
                    "date": flight_date or f.get("date"),
                    "takeoff_time": takeoff_time,
                    "landing_time": landing_time,
                    "duration_seconds": duration,
                    "takeoff_lat": takeoff_lat,
                    "takeoff_lon": takeoff_lon,
                    "landing_lat": landing_lat,
                    "landing_lon": landing_lon,
                    "takeoff_address": f.get("takeoff_address") or f.get("location"),
                    "pilot_name": f.get("pilot_name") or f.get("operator_name"),
                    "vehicle_serial": f.get("vehicle_serial") or f.get("serial_number"),
                    "max_altitude_m": f.get("max_altitude_m") or f.get("max_altitude"),
                    "max_speed_mps": f.get("max_speed_mps") or f.get("max_speed"),
                    "distance_m": f.get("distance_m") or f.get("total_distance"),
                    "battery_serial": f.get("battery_serial"),
                })

            logger.info("Fetched %d flights from Skydio", len(flights))
            return flights
        except Exception as exc:
            logger.error("Failed to sync Skydio flights: %s", exc)
            return []

    def sync_batteries(self, creds: ProviderCredentials) -> list[dict]:
        """Fetch batteries from Skydio Cloud."""
        try:
            raw = self._paginate(f"{BASE_URL}/batteries", creds)
            batteries = []
            for b in raw:
                batteries.append({
                    "serial_number": b.get("serial_number", b.get("battery_serial", "")),
                    "manufacturer": "Skydio",
                    "model": b.get("model") or b.get("battery_type"),
                    "vehicle_model": b.get("vehicle_model"),
                    "cycle_count": b.get("cycle_count", 0),
                    "health_pct": b.get("health_pct") or b.get("state_of_health"),
                    "skydio_battery_serial": b.get("serial_number", b.get("battery_serial", "")),
                    "api_provider": "skydio",
                })
            logger.info("Fetched %d batteries from Skydio", len(batteries))
            return batteries
        except Exception as exc:
            logger.error("Failed to sync Skydio batteries: %s", exc)
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
            logger.error("Failed to sync Skydio controllers: %s", exc)
            return []

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

            raw = body if isinstance(body, list) else (body.get("data") or body.get("points") or [])
            points = []
            for p in raw:
                points.append({
                    "timestamp_ms": p.get("timestamp_ms") or p.get("timestamp"),
                    "lat": p.get("lat") or p.get("latitude"),
                    "lon": p.get("lon") or p.get("longitude"),
                    "altitude_m": p.get("altitude_m") or p.get("altitude"),
                    "speed_mps": p.get("speed_mps") or p.get("speed"),
                    "battery_pct": p.get("battery_pct") or p.get("battery_percent"),
                    "battery_voltage": p.get("battery_voltage"),
                    "heading_deg": p.get("heading_deg") or p.get("heading"),
                    "pitch_deg": p.get("pitch_deg") or p.get("pitch"),
                    "roll_deg": p.get("roll_deg") or p.get("roll"),
                    "satellites": p.get("satellites") or p.get("gps_satellites"),
                })

            logger.info("Fetched %d telemetry points for flight %s", len(points), flight_id)
            return points
        except Exception as exc:
            logger.error("Failed to fetch telemetry for flight %s: %s", flight_id, exc)
            return []

    def sync_media(self, creds: ProviderCredentials, since: str | None = None) -> list[dict]:
        """Fetch media files from Skydio Cloud."""
        try:
            # Note: Skydio media endpoint doesn't support date_from filtering
            raw = self._paginate(f"{BASE_URL}/media/files", creds)
            media = []
            for m in raw:
                captured_time = None
                captured_str = m.get("captured_time") or m.get("created_at") or m.get("timestamp")
                if captured_str:
                    try:
                        captured_time = datetime.fromisoformat(captured_str.replace("Z", "+00:00"))
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
            logger.error("Failed to sync Skydio media: %s", exc)
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
            logger.error("Failed to sync Skydio docks: %s", exc)
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
            logger.error("Failed to sync Skydio sensor packages: %s", exc)
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
            logger.error("Failed to sync Skydio attachments: %s", exc)
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
            logger.error("Failed to sync Skydio users: %s", exc)
            return []


# Register the provider with the registry
register_provider(SkydioProvider)
