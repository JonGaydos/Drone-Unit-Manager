from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

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


@router.put("/bulk")
def set_settings_bulk(data: list[SettingValue], db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    for item in data:
        setting = db.query(Setting).filter(Setting.key == item.key).first()
        if setting:
            setting.value = item.value
        else:
            setting = Setting(key=item.key, value=item.value)
            db.add(setting)
    db.commit()
    return {"ok": True}
