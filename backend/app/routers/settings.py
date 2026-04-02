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
    "org_name", "org_logo", "skydio_api_token", "skydio_token_id",
    "sync_interval", "sidebar_config", "weather_wind_threshold",
    "weather_visibility_threshold", "weather_ceiling_threshold",
    "weather_temp_min", "weather_temp_max", "weather_location",
    "cert_types_config", "cert_status_labels", "mission_purposes",
    "weather_location_lat", "weather_location_lon",
    "adsb_default_lat", "adsb_default_lon", "adsb_radius_nm", "adsb_refresh_seconds",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_from_address", "smtp_from_name", "smtp_tls", "smtp_enabled",
    "weather_thresholds",
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


# Keys whose values contain secrets and must be partially redacted in responses
MASKED_KEYS = {"skydio_api_token", "smtp_password"}


@router.get("", response_model=list[SettingOut], responses=responses(401))
def list_settings(db: DBSession, user: CurrentUser):
    """List all settings. Secret values are partially masked in the response."""
    settings = db.query(Setting).all()
    result = []
    for s in settings:
        value = s.value
        if s.key in MASKED_KEYS and value:
            value = value[:8] + "..." + value[-4:] if len(value) > 12 else "****"
        result.append(SettingOut(key=s.key, value=value))
    return result


@router.get("/{key}", response_model=SettingOut, responses=responses(401))
def get_setting(key: str, db: DBSession, user: CurrentUser):
    """Retrieve a single setting by key. Returns empty value if not found."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        return SettingOut(key=key, value="")
    value = setting.value
    if key in MASKED_KEYS and value:
        value = value[:8] + "..." + value[-4:] if len(value) > 12 else "****"
    return SettingOut(key=key, value=value)


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


ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


@router.post("/logo", responses=responses(400, 401, 413))
async def upload_logo(file: UploadFile, db: DBSession, user: AdminUser):
    """Upload or replace the organization logo. Admin only."""
    upload_dir = Path(app_settings.UPLOAD_DIR) / "org"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower() or ".png"
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed for logo.")
    for old in upload_dir.glob("logo.*"):
        old.unlink()
    filepath = upload_dir / f"logo{ext}"
    content = await file.read()
    if len(content) > app_settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {app_settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB")
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
    for ext in [".png", ".jpg", ".jpeg", ".webp", ".svg"]:
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
        # Don't overwrite real token with masked value from frontend
        if item.key in MASKED_KEYS and "..." in (item.value or ""):
            continue
        setting = db.query(Setting).filter(Setting.key == item.key).first()
        if setting:
            setting.value = item.value
        else:
            setting = Setting(key=item.key, value=item.value)
            db.add(setting)
    db.commit()
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
