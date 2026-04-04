"""Authentication, authorization, and user management endpoints.

Provides JWT-based auth, role-based access control, rate-limited login,
password policy enforcement, and full CRUD for user accounts.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from time import time
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import USER_NOT_FOUND
from app.database import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, UserOut, UserCreate, UserUpdate, ChangePasswordRequest, AdminResetPasswordRequest, SetupRequest
from app.responses import responses

DBSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt hash as a UTF-8 string.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        password: The plaintext password to check.
        hashed: The stored bcrypt hash.

    Returns:
        True if the password matches the hash.
    """
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    """Create a signed JWT access token for the given user.

    Args:
        user_id: The database ID of the authenticated user.

    Returns:
        An encoded JWT string with the user ID and expiration claim.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: DBSession,
) -> User:
    """FastAPI dependency that extracts and validates the current user from the JWT.

    Args:
        credentials: The Bearer token from the Authorization header.
        db: Database session.

    Returns:
        The authenticated User ORM object.

    Raises:
        HTTPException: 401 if the token is missing, invalid, or the user is inactive.
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=USER_NOT_FOUND)
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Dependency that restricts access to admin-role users only."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_supervisor(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Allow admin or supervisor roles."""
    if user.role not in ("admin", "supervisor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires supervisor role or higher")
    return user


def require_pilot(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Allow admin, supervisor, or pilot roles."""
    if user.role not in ("admin", "supervisor", "pilot"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires pilot role or higher")
    return user


def require_manager(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Legacy alias — allow admin, supervisor, or pilot roles."""
    if user.role not in ("admin", "supervisor", "manager", "pilot"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return user


# In-memory rate limiter for login attempts (per IP, sliding window)
_login_attempts = defaultdict(list)  # ip -> [timestamps]
_RATE_LIMIT = 5  # max attempts per window
_RATE_WINDOW = 60  # window size in seconds


def _check_rate_limit(request):
    """Enforce per-IP login rate limiting using a sliding time window.

    Args:
        request: The incoming FastAPI Request (used to extract client IP).

    Raises:
        HTTPException: 429 if the IP has exceeded the allowed attempts.
    """
    ip = request.client.host if request.client else "unknown"
    now = time()
    # Prune expired timestamps outside the current window
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _RATE_WINDOW]
    if len(_login_attempts[ip]) >= _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    _login_attempts[ip].append(now)


def _validate_password(password: str):
    """Enforce password complexity requirements (min 12 chars, uppercase, digit).

    Args:
        password: The candidate password string.

    Raises:
        HTTPException: 400 if any policy requirement is not met.
    """
    if len(password) < 12:
        raise HTTPException(400, "Password must be at least 12 characters")
    if not any(c.isupper() for c in password):
        raise HTTPException(400, "Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in password):
        raise HTTPException(400, "Password must contain at least one number")


@router.get("/setup-required")
def check_setup_required(db: DBSession):
    """Check if initial setup is needed (no users exist)."""
    user_count = db.query(User).count()
    return {"setup_required": user_count == 0}


@router.post("/setup", responses=responses(400, 403))
def initial_setup(data: SetupRequest, db: DBSession):
    """Create the first admin account. Only works when no users exist."""
    user_count = db.query(User).count()
    if user_count > 0:
        raise HTTPException(403, "Setup already completed. Use the login page.")

    username = data.username.strip()
    password = data.password
    display_name = data.display_name.strip()
    org_name = data.org_name.strip()

    if not username or len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")

    _validate_password(password)

    from app.models.setting import Setting
    from app.models.folder import Folder
    from app.models.flight import FlightPurpose
    from app.models.pilot import Pilot

    email = data.email.strip() if data.email else ""

    # Split display name into first/last for pilot record
    name_parts = (display_name or username).split(None, 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    # Create pilot record for the admin user
    pilot = Pilot(
        first_name=first_name,
        last_name=last_name,
        email=email or None,
        status="active",
    )
    db.add(pilot)
    db.flush()

    # Create admin user linked to the pilot
    admin = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name or username,
        role="admin",
        email=email or None,
        pilot_id=pilot.id,
    )
    db.add(admin)

    # Set org name if provided
    if org_name:
        db.add(Setting(key="org_name", value=org_name))

    # Seed default folders
    for name in ["General", "Certifications", "Insurance", "Maintenance", "Reports"]:
        db.add(Folder(name=name, is_system=True))

    # Seed default flight purposes
    DEFAULT_PURPOSES = [
        "Training", "Demonstration", "Manhunt", "Security", "Other Agency Assist",
        "Search Warrant", "Missing Person", "Photograph Request", "Map Scan",
        "CPTED", "Citizen Assist", "Fire", "Patrol", "Investigation",
        "Search & Rescue", "Surveillance", "Mapping", "Inspection", "Other",
    ]
    for i, name in enumerate(DEFAULT_PURPOSES):
        db.add(FlightPurpose(name=name, sort_order=i))

    db.commit()
    db.refresh(admin)

    # Generate token so they're logged in immediately
    token = create_token(admin.id)
    return {
        "token": token,
        "user": {"id": admin.id, "username": admin.username, "display_name": admin.display_name, "role": admin.role}
    }


@router.post("/login", response_model=LoginResponse, responses=responses(401, 403))
def login(req: LoginRequest, request: Request, db: DBSession):
    """Authenticate a user with username and password.

    Applies rate limiting, logs success/failure to the audit trail,
    and returns a JWT on success.

    Args:
        req: Login credentials (username, password).
        request: FastAPI request (for rate-limit IP extraction).
        db: Database session.

    Returns:
        LoginResponse with JWT token and user profile.
    """
    _check_rate_limit(request)
    from app.services.audit import log_action
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        log_action(db, None, req.username, "login_failed", "auth", details=f"Failed login attempt for '{req.username}'")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    token = create_token(user.id)
    log_action(db, user.id, user.display_name, "login", "auth", details="Successful login")
    db.commit()
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(user: Annotated[User, Depends(get_current_user)]):
    """Return the currently authenticated user's profile."""
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(data: UserUpdate, user: Annotated[User, Depends(get_current_user)], db: DBSession):
    """Update the current user's own profile (theme, display name)."""
    if data.theme is not None:
        user.theme = data.theme
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.email is not None:
        user.email = data.email
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users", response_model=UserOut, responses=responses(409))
def create_user(data: UserCreate, admin: Annotated[User, Depends(require_admin)], db: DBSession):
    """Create a new user account. Admin only.

    Args:
        data: New user details (username, password, role, etc.).
        admin: The authenticated admin performing the action.
        db: Database session.

    Returns:
        The newly created user profile.
    """
    from app.services.audit import log_action
    _validate_password(data.password)
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    # Auto-populate email from linked pilot if not provided
    email = data.email
    if not email and data.pilot_id:
        from app.models.pilot import Pilot
        pilot = db.query(Pilot).filter(Pilot.id == data.pilot_id).first()
        if pilot and pilot.email:
            email = pilot.email

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        role=data.role,
        pilot_id=data.pilot_id,
        email=email,
    )
    db.add(user)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "user", user.id, user.display_name, details=f"Created user '{user.username}' with role '{user.role}'")
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
def list_users(admin: Annotated[User, Depends(require_admin)], db: DBSession):
    """List all user accounts. Admin only."""
    return [UserOut.model_validate(u) for u in db.query(User).all()]


@router.post("/change-password", responses=responses(400))
def change_password(req: ChangePasswordRequest, user: Annotated[User, Depends(get_current_user)], db: DBSession):
    """Change the current user's own password after verifying the old one."""
    from app.services.audit import log_action
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    _validate_password(req.new_password)
    user.password_hash = hash_password(req.new_password)
    log_action(db, user.id, user.display_name, "password_change", "user", user.id, user.display_name)
    db.commit()
    return {"ok": True, "message": "Password changed successfully"}


@router.patch("/users/{user_id}", response_model=UserOut, responses=responses(404))
def update_user(user_id: int, data: UserUpdate, admin: Annotated[User, Depends(require_admin)], db: DBSession):
    """Update a user's profile, role, or active status. Admin only."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
    if data.display_name is not None:
        target.display_name = data.display_name
    if data.role is not None:
        target.role = data.role
    if data.is_active is not None:
        target.is_active = data.is_active
    if data.pilot_id is not None:
        target.pilot_id = data.pilot_id if data.pilot_id != 0 else None
        # Auto-sync email from linked pilot if user has no email
        if target.pilot_id and not target.email:
            from app.models.pilot import Pilot
            pilot = db.query(Pilot).filter(Pilot.id == target.pilot_id).first()
            if pilot and pilot.email:
                target.email = pilot.email
    if data.email is not None:
        target.email = data.email
    db.commit()
    db.refresh(target)
    return UserOut.model_validate(target)


@router.post("/users/{user_id}/reset-password", responses=responses(404))
def admin_reset_password(user_id: int, req: AdminResetPasswordRequest, admin: Annotated[User, Depends(require_admin)], db: DBSession):
    """Reset another user's password without requiring the old one. Admin only."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
    _validate_password(req.new_password)
    target.password_hash = hash_password(req.new_password)
    db.commit()
    return {"ok": True, "message": f"Password reset for {target.username}"}


@router.delete("/users/{user_id}", responses=responses(400, 404))
def delete_user(user_id: int, admin: Annotated[User, Depends(require_admin)], db: DBSession):
    """Permanently delete a user account. Admin only. Cannot delete self."""
    from app.services.audit import log_action
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target_name = target.display_name
    target_username = target.username
    db.delete(target)
    log_action(db, admin.id, admin.display_name, "delete", "user", user_id, target_name, details=f"Deleted user '{target_username}'")
    db.commit()
    return {"ok": True}
