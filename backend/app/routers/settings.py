"""Application settings endpoints for managing organization configuration.

Supports key-value settings with an allowlist, secret masking for API tokens,
organization logo upload, and bulk updates.
"""

import json
import math
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings as app_settings
from app.constants import LOGO_VIEW_PATH, SECRET_KEYS
from app.deps import AdminForm, DBSession, CurrentUser, AdminUser
from app.models.setting import Setting
from app.responses import responses

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Whitelist of setting keys that can be read/written via the API
ALLOWED_SETTING_KEYS = {
    "org_name", "org_logo", "display_timezone", "skydio_api_token", "skydio_token_id",
    "sync_interval", "telemetry_sync_interval", "sidebar_config", "weather_wind_threshold",
    "weather_visibility_threshold", "weather_ceiling_threshold",
    "weather_temp_min", "weather_temp_max", "weather_location",
    "cert_types_config", "cert_status_labels", "mission_purposes",
    "weather_location_lat", "weather_location_lon",
    "adsb_default_lat", "adsb_default_lon", "adsb_radius_nm", "adsb_refresh_seconds",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_from_address", "smtp_from_name", "smtp_tls", "smtp_enabled",
    "weather_thresholds",
    "drone_location_places",
    "org_default_lat", "org_default_lon", "org_location_name",
    "backup_enabled", "backup_retention", "backup_hour",
    "idle_lock_minutes",
    "sidebar_show_groups",
}

# Minutes of no input before a browser locks. One value for every role.
IDLE_LOCK_KEY = "idle_lock_minutes"
IDLE_LOCK_CHOICES = frozenset({"30", "60", "120", "240", "360", "480", "720"})


class SettingValue(BaseModel):
    """Request schema for creating or updating a single setting."""
    key: str
    value: str


class SettingOut(BaseModel):
    """Response schema for a setting (values in MASKED_KEYS are partially redacted)."""
    key: str
    value: str

    model_config = {"from_attributes": True}


# Placeholder returned in place of a stored secret; never written back.
REDACTED_MARKER = "********"

# Keys safe to expose to any authenticated user (used by sidebar, dashboards,
# weather widget, etc.). Everything else is admin-only.
PUBLIC_KEYS = {
    "org_name", "org_logo", "display_timezone",
    "sidebar_config", "sidebar_show_groups", "telemetry_sync_interval",
    "weather_wind_threshold", "weather_visibility_threshold",
    "weather_ceiling_threshold", "weather_temp_min", "weather_temp_max",
    "weather_location", "weather_location_lat", "weather_location_lon",
    "weather_thresholds",
    "adsb_default_lat", "adsb_default_lon", "adsb_radius_nm", "adsb_refresh_seconds",
    "cert_types_config", "cert_status_labels", "mission_purposes",
    "drone_location_places",
    "org_default_lat", "org_default_lon", "org_location_name",
    "idle_lock_minutes",
}


# Skydio credentials pasted from a browser often carry a trailing space or
# newline. Mail credentials are kept as typed.
TRIMMED_KEYS = {"skydio_api_token", "skydio_token_id"}


def _trimmed(key: str, value: str) -> str:
    """The value without surrounding whitespace when the key holds a credential."""
    return value.strip() if key in TRIMMED_KEYS else value


def _check_idle_lock(key: str, value: str) -> None:
    """Refuse an idle lock value outside the offered choices."""
    if key == IDLE_LOCK_KEY and value not in IDLE_LOCK_CHOICES:
        raise HTTPException(422, "Idle lock must be 30, 60, 120, 240, 360, 480 or 720 minutes")


# Settings stored as the text "true" or "false".
BOOLEAN_KEYS = {"sidebar_show_groups"}


# Each GO limit against its CAUTION limit: (go key, caution key, label, go must be
# at most caution). Wind is worse when higher, the others when lower.
_THRESHOLD_PAIRS = (
    ("wind_sustained_go", "wind_sustained_caution", "Wind sustained", True),
    ("wind_gusts_go", "wind_gusts_caution", "Wind gusts", True),
    ("visibility_go", "visibility_caution", "Visibility", False),
    ("ceiling_go", "ceiling_caution", "Ceiling", False),
    ("temp_low_go", "temp_low_caution", "Temp low", False),
)
# Temperatures may be below zero; every other threshold may not.
_SIGNED_THRESHOLDS = {"temp_low_go", "temp_low_caution", "temp_high_go"}


def _check_weather_thresholds(value: str) -> None:
    """Refuse weather thresholds that are not a JSON object of known numeric
    limits, a negative distance, speed or amount, or a GO limit beyond its
    CAUTION limit (checked over the defaults for keys left out)."""
    from app.routers.weather import DEFAULT_THRESHOLDS
    try:
        custom = json.loads(value)
    except (TypeError, ValueError):
        raise HTTPException(422, "Weather thresholds must be a JSON object") from None
    if not isinstance(custom, dict):
        raise HTTPException(422, "Weather thresholds must be a JSON object")
    for name, limit in custom.items():
        if name not in DEFAULT_THRESHOLDS:
            raise HTTPException(422, f"Unknown weather threshold '{name}'")
        if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not math.isfinite(limit):
            raise HTTPException(422, f"Weather threshold '{name}' must be a number")
        if limit < 0 and name not in _SIGNED_THRESHOLDS:
            raise HTTPException(422, f"Weather threshold '{name}' must not be negative")
    t = {**DEFAULT_THRESHOLDS, **custom}
    for go, caution, label, go_is_lower in _THRESHOLD_PAIRS:
        if (t[go] > t[caution]) if go_is_lower else (t[go] < t[caution]):
            relation = "above" if go_is_lower else "below"
            raise HTTPException(422, f"{label} GO ({t[go]}) must not be {relation} CAUTION ({t[caution]})")


def _check_value(key: str, value: str) -> None:
    """Refuse a value the key cannot hold (422)."""
    _check_idle_lock(key, value)
    if key in BOOLEAN_KEYS and value not in ("true", "false"):
        raise HTTPException(422, f"{key} must be true or false")
    if key == "weather_thresholds":
        _check_weather_thresholds(value)
    if key == "org_name" and not value.strip():
        raise HTTPException(422, "Organization name is required")


def _redact_value(key: str, value: str | None) -> str:
    """Replace secret values with a presence marker so the UI can show
    'configured' / 'not set' without exposing entropy. Earlier code returned
    the first 8 + last 4 chars which leaks meaningful key material."""
    if value is None:
        return ""
    if key in SECRET_KEYS:
        return REDACTED_MARKER if value else ""
    return value


@router.get("", response_model=list[SettingOut], responses=responses(401))
def list_settings(db: DBSession, user: CurrentUser):
    """List settings. Non-admin users only see PUBLIC_KEYS; admins see
    everything with secret values redacted to a presence marker."""
    is_admin = user.role == "admin"
    rows = db.query(Setting).all()
    result = []
    for s in rows:
        if not is_admin and s.key not in PUBLIC_KEYS:
            continue
        result.append(SettingOut(key=s.key, value=_redact_value(s.key, s.value)))
    return result


@router.get("/{key}", response_model=SettingOut, responses=responses(401, 403))
def get_setting(key: str, db: DBSession, user: CurrentUser):
    """Retrieve a single setting. Non-admin users get 403 on non-public keys."""
    if user.role != "admin" and key not in PUBLIC_KEYS:
        raise HTTPException(403, "Access denied")
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        return SettingOut(key=key, value="")
    return SettingOut(key=key, value=_redact_value(key, setting.value))


@router.put("", responses=responses(400, 401, 422))
def set_setting(data: SettingValue, db: DBSession, admin: AdminUser):
    """Create or update a single setting. Admin only. Key must be in ALLOWED_SETTING_KEYS."""
    if data.key not in ALLOWED_SETTING_KEYS:
        raise HTTPException(400, f"Setting key '{data.key}' is not allowed")
    _check_value(data.key, data.value)
    data.value = _trimmed(data.key, data.value)
    from app.services.audit import log_action
    setting = db.query(Setting).filter(Setting.key == data.key).first()
    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=data.key, value=data.value)
        db.add(setting)
    log_action(db, admin.id, admin.display_name, "update", "setting", entity_name=data.key,
               details=f"Updated setting '{data.key}'")
    db.commit()
    return {"ok": True}


ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
# The stored logo's extension comes from what the file holds, not its name, so
# it is always served as the type it is.
LOGO_EXT_BY_TYPE = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}


@router.post("/logo", responses=responses(400, 401, 413))
async def upload_logo(upload: AdminForm, db: DBSession):
    """Upload or replace the organization logo. Admin only."""
    file = upload.file
    user = upload.user
    upload_dir = Path(app_settings.UPLOAD_DIR) / "org"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower()
    if ext and ext not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed for logo.")
    content = await file.read()
    if len(content) > app_settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {app_settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB")
    from app.services.file_validation import sniff_type
    ext = LOGO_EXT_BY_TYPE.get(sniff_type(content[:512]))
    if ext is None:
        raise HTTPException(400, "Logo must be a PNG, JPEG or WebP image")
    filepath = upload_dir / f"logo{ext}"
    await anyio.Path(filepath).write_bytes(content)
    for old in upload_dir.glob("logo.*"):
        if old.name != filepath.name:
            old.unlink()
    setting = db.query(Setting).filter(Setting.key == "org_logo").first()
    if setting:
        setting.value = LOGO_VIEW_PATH
    else:
        db.add(Setting(key="org_logo", value=LOGO_VIEW_PATH))
    from app.services.audit import log_action
    log_action(db, user.id, user.display_name, "update", "setting", entity_name="org_logo",
               details="Replaced the organization logo")
    db.commit()
    return {"ok": True, "logo_url": LOGO_VIEW_PATH}


@router.get("/logo/view", responses=responses(404))
def view_logo():
    """Serve the organization logo image file."""
    logo_dir = Path(app_settings.UPLOAD_DIR) / "org"
    from app.services.file_validation import mime_for_filename
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        p = logo_dir / f"logo{ext}"
        if p.exists():
            return FileResponse(p, media_type=mime_for_filename(p.name))
    raise HTTPException(404, "No logo found")


def _upsert_settings(db, data) -> list[str]:
    """Write each allowed setting, skipping unknown keys and never overwriting a
    stored secret with an empty or redacted placeholder value. Returns the keys
    whose value actually changed."""
    changed = []
    for item in data:
        if item.key not in ALLOWED_SETTING_KEYS:
            continue
        item.value = _trimmed(item.key, item.value)
        if item.key in SECRET_KEYS and (item.value or "") in ("", REDACTED_MARKER):
            continue
        setting = db.query(Setting).filter(Setting.key == item.key).first()
        if setting:
            if setting.value != item.value:
                changed.append(item.key)
            setting.value = item.value
        else:
            changed.append(item.key)
            db.add(Setting(key=item.key, value=item.value))
    return changed


def _interval_from(data, key) -> int | None:
    """The last valid int value for setting `key` in `data`; None if absent or
    unparseable (an unparseable value keeps the previous valid one, as before)."""
    interval = None
    for item in data:
        if item.key == key and item.value:
            try:
                interval = int(item.value)
            except ValueError:
                pass
    return interval


@router.put("/bulk", responses=responses(401, 422))
def set_settings_bulk(data: list[SettingValue], db: DBSession, admin: AdminUser):
    """Update multiple settings in a single request. Admin only.

    Skips keys not in ALLOWED_SETTING_KEYS and ignores masked placeholder
    values to avoid overwriting real secrets with redacted strings.
    """
    for item in data:
        _check_value(item.key, item.value)
    changed = _upsert_settings(db, data)
    if changed:
        # Key names only: several of these hold credentials.
        from app.services.audit import log_action
        log_action(db, admin.id, admin.display_name, "update", "setting",
                   details=f"Updated settings: {', '.join(sorted(set(changed)))}")
    db.commit()

    # Reschedule the sync/telemetry jobs only when their interval was in the request.
    if any(item.key == "sync_interval" for item in data):
        from app.services.scheduler import reschedule_sync
        reschedule_sync(_interval_from(data, "sync_interval"))
    if any(item.key == "telemetry_sync_interval" for item in data):
        from app.services.scheduler import reschedule_telemetry_sync
        reschedule_telemetry_sync(_interval_from(data, "telemetry_sync_interval"))

    return {"ok": True}


@router.post("/smtp/test", responses=responses(400, 401, 429, 500))
def test_smtp(db: DBSession, admin: AdminUser):
    """Send a test email to verify SMTP configuration."""
    from app.services.email_digest import send_email
    from app.models.pilot import Pilot

    # Resolve email: user.email → linked pilot.email
    admin_email = admin.email
    if not admin_email and admin.pilot_id:
        pilot = db.query(Pilot).filter(Pilot.id == admin.pilot_id).first()
        if pilot and pilot.email:
            admin_email = pilot.email
    if not admin_email:
        raise HTTPException(400, "No email address found. Add an email to your linked pilot profile or user account in Settings > Users.")

    from app.routers.notifications import check_smtp_test_rate
    check_smtp_test_rate(admin.id)
    success = send_email(
        admin_email,
        "Drone Unit Manager — SMTP Test",
        "<h2>SMTP Test Successful</h2><p>Your email configuration is working correctly.</p>",
        db,
    )
    if success:
        return {"ok": True, "message": f"Test email sent to {admin_email}"}
    else:
        raise HTTPException(500, "Failed to send test email. Check your SMTP settings.")
