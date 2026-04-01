"""Shared FastAPI dependency type aliases using Annotated.

Centralizes common dependency injection patterns so routers can use
clean type hints instead of repeating Depends() calls.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db, get_telemetry_db
from app.models.user import User
from app.routers.auth import (
    get_current_user,
    require_admin,
    require_manager,
    require_pilot,
    require_supervisor,
)

DBSession = Annotated[Session, Depends(get_db)]
TelemetryDBSession = Annotated[Session, Depends(get_telemetry_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
SupervisorUser = Annotated[User, Depends(require_supervisor)]
PilotUser = Annotated[User, Depends(require_pilot)]
ManagerUser = Annotated[User, Depends(require_manager)]
