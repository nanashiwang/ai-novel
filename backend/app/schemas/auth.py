from __future__ import annotations

from .common import APIModel


class CurrentUserResponse(APIModel):
    id: str
    email: str
    platform_role: str
    organization_role: str
    organization_id: str
    organization_name: str
    plan_code: str
