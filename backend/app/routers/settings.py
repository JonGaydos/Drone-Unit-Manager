"""Application settings endpoints for managing organization configuration.

Supports key-value settings with an allowlist, secret masking for API tokens,
organization logo upload, and bulk updates.
"""

from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings as app_settings
from app.constants import LOGO_VIEW_PATH
from app.deps import DBSession, CurrentUser, AdminUser
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
}


class SettingValue(BaseModel):
    """Request schema for creating or updating a single setting."""
    key: str
    value: str


class SettingOut(BaseModel):
    """Response schema for a setting (values in MASKED_KEYS are partially redacted)."""
    key: str
    value: str

    model_config = {"from_attributes": True}


# Keys whose values contain secrets — never returned to any role.
SECRET_KEYS = {
    "skydio_api_token", "skydio_token_id",
    "smtp_password",
}

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
}


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


@router.put("", responses=responses(400, 401))
def set_setting(data: SettingValue, db: DBSession, admin: AdminUser):
    """Create or update a single setting. Admin only. Key must be in ALLOWED_SETTING_KEYS."""
    if data.key not in ALLOWED_SETTING_KEYS:
        raise HTTPException(400, f"Setting key '{data.key}' is not allowed")
    from app.services.audit import log_action
    setting = db.query(Setting).filter(Setting.key == data.key).first()
    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=data.key, value=data.value)
        db.add(setting)
    log_action(db, admin.id, admin.display_name, "update", "setting", details=f"Updated setting '{data.key}'")
    db.commit()
    return {"ok": True}


ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@router.post("/logo", responses=responses(400, 401, 413))
async def upload_logo(file: UploadFile, db: DBSession, user: AdminUser):
    """Upload or replace the organization logo. Admin only."""
    upload_dir = Path(app_settings.UPLOAD_DIR) / "org"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower() or ".png"
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed for logo.")
    content = await file.read()
    if len(content) > app_settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {app_settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB")
    from app.services.file_validation import is_image
    if not is_image(content[:512]):
        raise HTTPException(400, "File content is not a recognized image")
    for old in upload_dir.glob("logo.*"):
        old.unlink()
    filepath = upload_dir / f"logo{ext}"
    await anyio.Path(filepath).write_bytes(content)
    setting = db.query(Setting).filter(Setting.key == "org_logo").first()
    if setting:
        setting.value = LOGO_VIEW_PATH
    else:
        db.add(Setting(key="org_logo", value=LOGO_VIEW_PATH))
    db.commit()
    return {"ok": True, "logo_url": LOGO_VIEW_PATH}


@router.get("/logo/view", responses=responses(404))
def view_logo():
    """Serve the organization logo image file."""
    logo_dir = Path(app_settings.UPLOAD_DIR) / "org"
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        p = logo_dir / f"logo{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(404, "No logo found")


@router.put("/bulk", responses=responses(401))
def set_settings_bulk(data: list[SettingValue], db: DBSession, admin: AdminUser):
    """Update multiple settings in a single request. Admin only.

    Skips keys not in ALLOWED_SETTING_KEYS and ignores masked placeholder
    values to avoid overwriting real secrets with redacted strings.
    """
    for item in data:
        if item.key not in ALLOWED_SETTING_KEYS:
            continue
        # Never write the redaction marker (or empty) over a stored secret.
        if item.key in SECRET_KEYS and (item.value or "") in ("", REDACTED_MARKER):
            continue
        setting = db.query(Setting).filter(Setting.key == item.key).first()
        if setting:
            setting.value = item.value
        else:
            setting = Setting(key=item.key, value=item.value)
            db.add(setting)
    db.commit()

    # Reschedule sync job if interval was changed
    if any(item.key == "sync_interval" for item in data):
        from app.services.scheduler import reschedule_sync
        interval_minutes = None
        for item in data:
            if item.key == "sync_interval" and item.value:
                try:
                    interval_minutes = int(item.value)
                except ValueError:
                    pass
        reschedule_sync(interval_minutes)

    # Reschedule telemetry job if its interval changed
    if any(item.key == "telemetry_sync_interval" for item in data):
        from app.services.scheduler import reschedule_telemetry_sync
        telemetry_minutes = None
        for item in data:
            if item.key == "telemetry_sync_interval" and item.value:
                try:
                    telemetry_minutes = int(item.value)
                except ValueError:
                    pass
        reschedule_telemetry_sync(telemetry_minutes)

    return {"ok": True}


@router.post("/smtp/test", responses=responses(400, 401, 500))
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
