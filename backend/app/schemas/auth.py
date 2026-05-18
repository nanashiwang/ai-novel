from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from .common import APIModel


class CurrentUserResponse(APIModel):
    id: str
    email: str
    display_name: str
    platform_role: str
    organization_role: str
    organization_id: str
    organization_name: str
    plan_code: str


class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=120)
    invitation_token: str | None = Field(default=None, max_length=128)


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class TokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: CurrentUserResponse
