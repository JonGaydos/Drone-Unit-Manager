"""Application settings endpoints for managing organization configuration.

Supports key-value settings with an allowlist, secret masking for API tokens,
organization logo upload, and bulk updates.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.models.setting import Setting
from app.models.user import User
from app.routers.auth import get_current_user, require_admin

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


@router.get("", response_model=list[SettingOut])
def list_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """List all settings. Secret values are partially masked in the response."""
    settings = db.query(Setting).all()
    result = []
    for s in settings:
        value = s.value
        if s.key in MASKED_KEYS and value:
            value = value[:8] + "..." + value[-4:] if len(value) > 12 else "****"
        result.append(SettingOut(key=s.key, value=value))
    return result


@router.get("/{key}", response_model=SettingOut)
def get_setting(key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Retrieve a single setting by key. Returns empty value if not found."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        return SettingOut(key=key, value="")
    value = setting.value
    if key in MASKED_KEYS and value:
        value = value[:8] + "..." + value[-4:] if len(value) > 12 else "****"
    return SettingOut(key=key, value=value)


@router.put("")
def set_setting(data: SettingValue, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
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


@router.post("/logo")
async def upload_logo(file: UploadFile, db: Session = Depends(get_db), user: User = Depends(require_admin)):
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
        raise HTTPException(413, f"File too large. Maximum size is {app_settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    with open(filepath, "wb") as f:
        f.write(content)
    setting = db.query(Setting).filter(Setting.key == "org_logo").first()
    if setting:
        setting.value = "/api/settings/logo/view"
    else:
        db.add(Setting(key="org_logo", value="/api/settings/logo/view"))
    db.commit()
    return {"ok": True, "logo_url": "/api/settings/logo/view"}


@router.get("/logo/view")
def view_logo():
    """Serve the organization logo image file."""
    logo_dir = Path(app_settings.UPLOAD_DIR) / "org"
    for ext in [".png", ".jpg", ".jpeg", ".webp", ".svg"]:
        p = logo_dir / f"logo{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(404, "No logo found")


@router.put("/bulk")
def set_settings_bulk(data: list[SettingValue], db: Session = Depends(get_db), admin: User = Depends(require_admin)):
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


@router.post("/smtp/test")
def test_smtp(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Send a test email to verify SMTP configuration."""
    from app.services.email_digest import send_email

    admin_email = admin.email
    if not admin_email:
        raise HTTPException(400, "Set your email address in your user profile first")

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
