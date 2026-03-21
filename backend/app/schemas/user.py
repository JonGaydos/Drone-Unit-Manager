from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    theme: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    theme: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserOut
