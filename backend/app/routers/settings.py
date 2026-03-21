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


class SettingValue(BaseModel):
    key: str
    value: str


class SettingOut(BaseModel):
    key: str
    value: str

    model_config = {"from_attributes": True}


# Keys that should be masked in the response (contain secrets)
MASKED_KEYS = {"skydio_api_token"}


@router.get("", response_model=list[SettingOut])
def list_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        return SettingOut(key=key, value="")
    value = setting.value
    if key in MASKED_KEYS and value:
        value = value[:8] + "..." + value[-4:] if len(value) > 12 else "****"
    return SettingOut(key=key, value=value)


@router.put("")
def set_setting(data: SettingValue, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    setting = db.query(Setting).filter(Setting.key == data.key).first()
    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=data.key, value=data.value)
        db.add(setting)
    db.commit()
    return {"ok": True}


@router.post("/logo")
async def upload_logo(file: UploadFile, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    upload_dir = Path(app_settings.UPLOAD_DIR) / "org"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old in upload_dir.glob("logo.*"):
        old.unlink()
    ext = Path(file.filename).suffix or ".png"
    filepath = upload_dir / f"logo{ext}"
    with open(filepath, "wb") as f:
        content = await file.read()
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
    logo_dir = Path(app_settings.UPLOAD_DIR) / "org"
    for ext in [".png", ".jpg", ".jpeg", ".webp", ".svg"]:
        p = logo_dir / f"logo{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(404, "No logo found")


@router.put("/bulk")
def set_settings_bulk(data: list[SettingValue], db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    for item in data:
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
