"""Sync orchestrator - coordinates data sync between Skydio Cloud API and local DB."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.integrations.base import ProviderCredentials
from app.integrations.registry import get_provider
from app.models.vehicle import Vehicle
from app.models.flight import Flight
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.sensor import SensorPackage
from app.models.attachment import Attachment
from app.models.media import MediaFile
from app.models.pilot import Pilot
from app.models.setting import Setting

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    vehicles_synced: int = 0
    flights_new: int = 0
    flights_skipped: int = 0
    batteries_synced: int = 0
    controllers_synced: int = 0
    docks_synced: int = 0
    sensors_synced: int = 0
    attachments_synced: int = 0
    media_synced: int = 0
    users_synced: int = 0
    errors: list[str] = field(default_factory=list)


def _get_setting(db: Session, key: str, default: str = "") -> str:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def _set_setting(db: Session, key: str, value: str):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)


def _build_creds(db: Session, provider_name: str) -> ProviderCredentials:
    """Build credentials from the settings table."""
    api_token = _get_setting(db, f"{provider_name}_api_token")
    token_id = _get_setting(db, f"{provider_name}_token_id")
    return ProviderCredentials(api_token=api_token, token_id=token_id)


class SyncManager:

    @staticmethod
    def test_connection(provider_name: str, db: Session) -> tuple[bool, str, dict]:
        """Test the API connection. Returns (ok, message, user_info)."""
        try:
            creds = _build_creds(db, provider_name)
            if not creds.api_token:
                return False, "API token not configured", {}

            provider = get_provider(provider_name)
            valid = provider.validate_credentials(creds)

            if not valid:
                return False, "Invalid credentials", {}

            # Get user info if available
            user_info = {}
            if hasattr(provider, "get_user_info"):
                user_info = provider.get_user_info(creds)

            return True, "Connection successful", user_info
        except Exception as exc:
            logger.error("Connection test failed for %s: %s", provider_name, exc)
            return False, f"Connection failed: {exc}", {}

    @staticmethod
    def sync_all(provider_name: str, db: Session) -> SyncResult:
        """Run a full sync from the given provider into the local database."""
        result = SyncResult()

        try:
            creds = _build_creds(db, provider_name)
            if not creds.api_token:
                result.errors.append("API token not configured")
                return result

            provider = get_provider(provider_name)
            last_sync = _get_setting(db, "last_sync_timestamp")
            since = last_sync if last_sync else None

        except Exception as exc:
            result.errors.append(f"Setup error: {exc}")
            logger.error("Sync setup error: %s", exc)
            return result

        # --- Sync users first (needed for pilot matching) ---
        skydio_users = []
        try:
            skydio_users = provider.sync_users(creds)
            result.users_synced = len(skydio_users)
            logger.info("Users sync: got %d users", len(skydio_users))
        except Exception as exc:
            result.errors.append(f"Users sync error: {exc}")
            logger.error("Users sync error: %s", exc, exc_info=True)

        # --- Sync vehicles ---
        try:
            vehicles_data = provider.sync_vehicles(creds)
            for v_data in vehicles_data:
                serial = v_data.get("skydio_vehicle_serial") or v_data.get("serial_number", "")
                if not serial:
                    continue

                existing = db.query(Vehicle).filter(
                    (Vehicle.skydio_vehicle_serial == serial) |
                    (Vehicle.serial_number == serial)
                ).first()

                if existing:
                    existing.manufacturer = v_data.get("manufacturer", existing.manufacturer)
                    existing.model = v_data.get("model", existing.model)
                    existing.api_provider = v_data.get("api_provider", "skydio")
                    if v_data.get("nickname") and not existing.nickname:
                        existing.nickname = v_data["nickname"]
                else:
                    vehicle = Vehicle(
                        serial_number=v_data.get("serial_number", serial),
                        manufacturer=v_data.get("manufacturer", "Skydio"),
                        model=v_data.get("model", "Unknown"),
                        skydio_vehicle_serial=serial,
                        api_provider=v_data.get("api_provider", "skydio"),
                        nickname=v_data.get("nickname"),
                    )
                    db.add(vehicle)

                result.vehicles_synced += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Vehicles sync error: {exc}")
            logger.error("Vehicles sync error: %s", exc)
            db.rollback()

        # --- Sync flights ---
        try:
            flights_data = provider.sync_flights(creds, since=since)
            for f_data in flights_data:
                ext_id = str(f_data.get("external_id", ""))
                if not ext_id:
                    continue

                # Check if flight already exists
                existing = db.query(Flight).filter(
                    Flight.external_id == ext_id,
                    Flight.api_provider == "skydio",
                ).first()

                if existing:
                    result.flights_skipped += 1
                    continue

                # Try to match vehicle
                vehicle_id = None
                vehicle_serial = f_data.get("vehicle_serial")
                if vehicle_serial:
                    vehicle = db.query(Vehicle).filter(
                        Vehicle.skydio_vehicle_serial == vehicle_serial
                    ).first()
                    if vehicle:
                        vehicle_id = vehicle.id

                # Try to match pilot by Skydio user name
                pilot_id = None
                pilot_name = f_data.get("pilot_name")
                if pilot_name and skydio_users:
                    pilot_id = _match_pilot(db, pilot_name)

                # Parse date
                flight_date = None
                date_val = f_data.get("date")
                if date_val:
                    if isinstance(date_val, str):
                        try:
                            flight_date = date.fromisoformat(date_val)
                        except ValueError:
                            pass
                    elif isinstance(date_val, date):
                        flight_date = date_val

                flight = Flight(
                    external_id=ext_id,
                    api_provider="skydio",
                    pilot_id=pilot_id,
                    vehicle_id=vehicle_id,
                    date=flight_date,
                    takeoff_time=f_data.get("takeoff_time"),
                    landing_time=f_data.get("landing_time"),
                    duration_seconds=f_data.get("duration_seconds"),
                    takeoff_lat=f_data.get("takeoff_lat"),
                    takeoff_lon=f_data.get("takeoff_lon"),
                    landing_lat=f_data.get("landing_lat"),
                    landing_lon=f_data.get("landing_lon"),
                    takeoff_address=f_data.get("takeoff_address"),
                    max_altitude_m=f_data.get("max_altitude_m"),
                    max_speed_mps=f_data.get("max_speed_mps"),
                    distance_m=f_data.get("distance_m"),
                    battery_serial=f_data.get("battery_serial"),
                    sensor_package=f_data.get("sensor_package"),
                    attachment_top=f_data.get("attachment_top"),
                    attachment_bottom=f_data.get("attachment_bottom"),
                    attachment_left=f_data.get("attachment_left"),
                    attachment_right=f_data.get("attachment_right"),
                    carrier=f_data.get("carrier"),
                    review_status="needs_review",
                    pilot_confirmed=False,
                )
                db.add(flight)
                result.flights_new += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Flights sync error: {exc}")
            logger.error("Flights sync error: %s", exc)
            db.rollback()

        # --- Sync batteries ---
        try:
            batteries_data = provider.sync_batteries(creds)
            for b_data in batteries_data:
                serial = b_data.get("serial_number", "")
                if not serial:
                    continue

                existing = db.query(Battery).filter(
                    Battery.serial_number == serial
                ).first()

                if existing:
                    existing.cycle_count = b_data.get("cycle_count", existing.cycle_count)
                    existing.health_pct = b_data.get("health_pct", existing.health_pct)
                    existing.api_provider = "skydio"
                else:
                    battery = Battery(
                        serial_number=serial,
                        manufacturer=b_data.get("manufacturer", "Skydio"),
                        model=b_data.get("model"),
                        vehicle_model=b_data.get("vehicle_model"),
                        cycle_count=b_data.get("cycle_count", 0),
                        health_pct=b_data.get("health_pct"),
                        skydio_battery_serial=b_data.get("skydio_battery_serial", serial),
                        api_provider="skydio",
                    )
                    db.add(battery)

                result.batteries_synced += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Batteries sync error: {exc}")
            logger.error("Batteries sync error: %s", exc)
            db.rollback()

        # --- Sync controllers ---
        try:
            controllers_data = provider.sync_controllers(creds)
            for c_data in controllers_data:
                serial = c_data.get("serial_number", "")
                if not serial:
                    continue

                existing = db.query(Controller).filter(
                    Controller.serial_number == serial
                ).first()

                if existing:
                    existing.api_provider = "skydio"
                    if c_data.get("model"):
                        existing.model = c_data["model"]
                else:
                    controller = Controller(
                        serial_number=serial,
                        manufacturer=c_data.get("manufacturer", "Skydio"),
                        model=c_data.get("model"),
                        skydio_controller_serial=c_data.get("skydio_controller_serial", serial),
                        api_provider="skydio",
                    )
                    db.add(controller)

                result.controllers_synced += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Controllers sync error: {exc}")
            logger.error("Controllers sync error: %s", exc)
            db.rollback()

        # --- Sync docks ---
        try:
            docks_data = provider.sync_docks(creds)
            for d_data in docks_data:
                serial = d_data.get("serial_number", "")
                if not serial:
                    continue

                existing = db.query(Dock).filter(
                    Dock.serial_number == serial
                ).first()

                if existing:
                    existing.api_provider = "skydio"
                    if d_data.get("name"):
                        existing.name = d_data["name"]
                    if d_data.get("lat"):
                        existing.lat = d_data["lat"]
                    if d_data.get("lon"):
                        existing.lon = d_data["lon"]
                    if d_data.get("location_name"):
                        existing.location_name = d_data["location_name"]
                else:
                    dock = Dock(
                        serial_number=serial,
                        name=d_data.get("name"),
                        location_name=d_data.get("location_name"),
                        lat=d_data.get("lat"),
                        lon=d_data.get("lon"),
                        skydio_dock_serial=d_data.get("skydio_dock_serial", serial),
                        api_provider="skydio",
                    )
                    db.add(dock)

                result.docks_synced += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Docks sync error: {exc}")
            logger.error("Docks sync error: %s", exc)
            db.rollback()

        # --- Sync sensor packages ---
        try:
            sensors_data = provider.sync_sensor_packages(creds)
            for s_data in sensors_data:
                serial = s_data.get("serial_number", "")
                if not serial:
                    continue

                existing = db.query(SensorPackage).filter(
                    SensorPackage.serial_number == serial
                ).first()

                if existing:
                    existing.api_provider = "skydio"
                    if s_data.get("name"):
                        existing.name = s_data["name"]
                    if s_data.get("type"):
                        existing.type = s_data["type"]
                else:
                    sensor = SensorPackage(
                        serial_number=serial,
                        name=s_data.get("name"),
                        type=s_data.get("type"),
                        manufacturer=s_data.get("manufacturer", "Skydio"),
                        model=s_data.get("model"),
                        skydio_serial=s_data.get("skydio_serial", serial),
                        api_provider="skydio",
                    )
                    db.add(sensor)

                result.sensors_synced += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Sensors sync error: {exc}")
            logger.error("Sensors sync error: %s", exc)
            db.rollback()

        # --- Sync attachments ---
        try:
            attachments_data = provider.sync_attachments(creds)
            for a_data in attachments_data:
                serial = a_data.get("serial_number", "")
                if not serial:
                    continue

                existing = db.query(Attachment).filter(
                    Attachment.serial_number == serial
                ).first()

                if existing:
                    existing.api_provider = "skydio"
                    if a_data.get("name"):
                        existing.name = a_data["name"]
                    if a_data.get("type"):
                        existing.type = a_data["type"]
                else:
                    attachment = Attachment(
                        serial_number=serial,
                        name=a_data.get("name"),
                        type=a_data.get("type"),
                        manufacturer=a_data.get("manufacturer", "Skydio"),
                        model=a_data.get("model"),
                        skydio_serial=a_data.get("skydio_serial", serial),
                        api_provider="skydio",
                    )
                    db.add(attachment)

                result.attachments_synced += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Attachments sync error: {exc}")
            logger.error("Attachments sync error: %s", exc)
            db.rollback()

        # --- Sync media ---
        try:
            media_data = provider.sync_media(creds, since=since)
            for m_data in media_data:
                ext_uuid = m_data.get("external_uuid", "")
                if not ext_uuid:
                    continue

                existing = db.query(MediaFile).filter(
                    MediaFile.external_uuid == ext_uuid
                ).first()

                if not existing:
                    media_file = MediaFile(
                        external_uuid=ext_uuid,
                        filename=m_data.get("filename", ""),
                        kind=m_data.get("kind", "photo"),
                        captured_time=m_data.get("captured_time"),
                        size_bytes=m_data.get("size_bytes"),
                        download_url=m_data.get("download_url"),
                        api_provider="skydio",
                    )
                    # Try to link to flight if we have a flight external_id
                    flight_ext_id = m_data.get("flight_external_id")
                    if flight_ext_id:
                        flight = db.query(Flight).filter(
                            Flight.external_id == str(flight_ext_id),
                            Flight.api_provider == "skydio",
                        ).first()
                        if flight:
                            media_file.flight_id = flight.id

                    db.add(media_file)
                    result.media_synced += 1

            db.flush()
        except Exception as exc:
            result.errors.append(f"Media sync error: {exc}")
            logger.error("Media sync error: %s", exc)
            db.rollback()

        # --- Commit and update last sync timestamp ---
        try:
            _set_setting(db, "last_sync_timestamp", datetime.utcnow().isoformat())
            _set_setting(db, "last_sync_provider", provider_name)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Commit error: {exc}")
            logger.error("Sync commit error: %s", exc)
            db.rollback()

        logger.info(
            "Sync complete: %d vehicles, %d new flights (%d skipped), %d batteries, %d errors",
            result.vehicles_synced, result.flights_new, result.flights_skipped,
            result.batteries_synced, len(result.errors),
        )

        return result


def _match_pilot(db: Session, pilot_name: str) -> int | None:
    """Try to match a Skydio pilot name to a local pilot by first+last name."""
    if not pilot_name:
        return None

    parts = pilot_name.strip().split()
    if len(parts) < 2:
        # Try matching just first name
        pilot = db.query(Pilot).filter(
            Pilot.first_name.ilike(parts[0]),
            Pilot.status == "active",
        ).first()
        return pilot.id if pilot else None

    first_name = parts[0]
    last_name = " ".join(parts[1:])

    pilot = db.query(Pilot).filter(
        Pilot.first_name.ilike(first_name),
        Pilot.last_name.ilike(last_name),
        Pilot.status == "active",
    ).first()

    return pilot.id if pilot else None
