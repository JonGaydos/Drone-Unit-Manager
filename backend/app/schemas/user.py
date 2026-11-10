import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Conservative email shape check. EmailStr is intentionally NOT used here
# because the email-validator package is not installed.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+\Z")


def _validate_optional_email(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    if not _EMAIL_RE.match(value):
        raise ValueError("invalid email address")
    return value


def _validate_display_name(value: Optional[str]) -> Optional[str]:
    """Trimmed; a blank name would show as nothing in lists and the audit log."""
    if value is None:
        return value
    value = value.strip()
    if not value:
        raise ValueError("display name is required")
    return value


# The roles the permission checks recognize. Anything else would create an
# account that silently matches no check.
Role = Literal["admin", "supervisor", "pilot", "viewer"]

# The theme ids the app offers (frontend ThemeContext THEMES).
Theme = Literal[
    "dark", "light", "glass", "grafana", "blue", "high-contrast", "midnight-slate",
    "ranger-green", "navy-brass", "arctic", "carbon-amber", "night-vision", "sandstone",
    "field-sage",
]


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=255)
    display_name: str = Field(max_length=255)
    role: Role = "viewer"
    pilot_id: Optional[int] = None
    email: Optional[str] = Field(default=None, max_length=255)

    _validate_email = field_validator("email")(_validate_optional_email)
    _validate_name = field_validator("display_name")(_validate_display_name)


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=255)
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    theme: Optional[Theme] = None
    pilot_id: Optional[int] = None
    email: Optional[str] = Field(default=None, max_length=255)

    _validate_email = field_validator("email")(_validate_optional_email)
    _validate_name = field_validator("display_name")(_validate_display_name)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=255)


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=255)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    theme: str
    pilot_id: Optional[int] = None
    email: Optional[str] = None
    created_at: datetime
    # Resolved values, filled in on the signed-in user's own responses only.
    permissions: dict[str, str] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=255)
    display_name: str = Field(default="", max_length=255)
    org_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    timezone: str = Field(default="America/Chicago", max_length=64)

    _validate_email = field_validator("email")(_validate_optional_email)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserOut
