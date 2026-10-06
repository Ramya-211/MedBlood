"""Pydantic request/response models for authentication and user management."""

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


class Role(str, Enum):
    """The ONLY three application roles. There is no patient role."""
    ADMIN = "ADMIN"
    PHARMACIST = "PHARMACIST"
    BLOOD_STAFF = "BLOOD_STAFF"


ROLE_HOME = {
    Role.ADMIN.value: "/admin/dashboard",
    Role.PHARMACIST.value: "/pharmacist/dashboard",
    Role.BLOOD_STAFF.value: "/blood/dashboard",
}


def _check_password(v: str) -> str:
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if v.strip() != v or not v.strip():
        raise ValueError("Password must not start or end with whitespace.")
    return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserPublic(BaseModel):
    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
    redirect_path: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = Field(min_length=1, max_length=128)
    role: Role

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        if not USERNAME_RE.match(v):
            raise ValueError("Username must be 3-64 characters: letters, digits, underscore, dot or hyphen.")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v):
        return _check_password(v)


class UserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    new_password: Optional[str] = None

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        if v is None:
            return v
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-64 characters: letters, digits, underscore, dot or hyphen."
            )
        return v

    @field_validator("new_password")
    @classmethod
    def _password(cls, v):
        return _check_password(v) if v is not None else v

    @field_validator("new_password")
    @classmethod
    def _password(cls, v):
        return _check_password(v) if v is not None else v


class UserList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[UserPublic]
