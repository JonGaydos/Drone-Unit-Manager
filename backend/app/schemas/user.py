import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Conservative email shape check. EmailStr is intentionally NOT used here
# because the email-validator package is not installed.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_optional_email(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    if not _EMAIL_RE.match(value):
        raise ValueError("invalid email address")
    return value


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=255)
    display_name: str = Field(max_length=255)
    role: str = "viewer"
    pilot_id: Optional[int] = None
    email: Optional[str] = Field(default=None, max_length=255)

    _validate_email = field_validator("email")(_validate_optional_email)


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = None
    is_active: Optional[bool] = None
    theme: Optional[str] = None
    pilot_id: Optional[int] = None
    email: Optional[str] = Field(default=None, max_length=255)

    _validate_email = field_validator("email")(_validate_optional_email)


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
