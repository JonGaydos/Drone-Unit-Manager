"""Sync API endpoints for triggering and monitoring Skydio Cloud sync."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.setting import Setting
from app.models.user import User
from app.routers.auth import require_admin
from app.services.sync_manager import SyncManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str
    user_info: dict = {}


class SyncResultResponse(BaseModel):
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
    errors: list[str] = []


class SyncStatusResponse(BaseModel):
    last_sync: str | None = None
    sync_interval: str | None = None
    provider: str | None = None


@router.post("/test", response_model=TestConnectionResponse)
def test_connection(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Test Skydio Cloud API connection with stored credentials."""
    ok, message, user_info = SyncManager.test_connection("skydio", db)
    return TestConnectionResponse(ok=ok, message=message, user_info=user_info)


@router.post("/now", response_model=SyncResultResponse)
def sync_now(
    full: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Run a sync from Skydio Cloud. Pass ?full=true for full historical sync."""
    logger.info("Manual sync triggered by admin (full=%s)", full)
    result = SyncManager.sync_all("skydio", db, full_sync=full)
    return SyncResultResponse(**asdict(result))


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Get the current sync status and configuration."""
    last_sync_setting = db.query(Setting).filter(Setting.key == "last_sync_timestamp").first()
    interval_setting = db.query(Setting).filter(Setting.key == "sync_interval").first()
    provider_setting = db.query(Setting).filter(Setting.key == "last_sync_provider").first()

    return SyncStatusResponse(
        last_sync=last_sync_setting.value if last_sync_setting else None,
        sync_interval=interval_setting.value if interval_setting else None,
        provider=provider_setting.value if provider_setting else None,
    )
