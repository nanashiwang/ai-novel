from __future__ import annotations

from dataclasses import dataclass
from fastapi import Header


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    platform_role: str
    organization_role: str


async def get_current_user(
    x_mock_user: str | None = Header(default=None, alias="X-Mock-User"),
) -> CurrentUser:
    if x_mock_user == "admin":
        return CurrentUser(
            id="user_admin",
            email="admin@novelflow.ai",
            platform_role="super_admin",
            organization_role="owner",
        )
    return CurrentUser(
        id="user_writer",
        email="writer@example.com",
        platform_role="user",
        organization_role="owner",
    )
