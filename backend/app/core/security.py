"""鉴权依赖。

从 `Authorization: Bearer <jwt>` 解析 access token，查 users 表，
返回封装好的 `CurrentUser`。彻底移除 X-Mock-User 提权漏洞。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.jwt_tokens import decode_token
from app.models.user import User
from app.repositories import UserRepository


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    display_name: str
    platform_role: str
    status: str
    # 由 tenant 解析填充，鉴权阶段先标记为 viewer
    organization_role: str = "viewer"
    # 鉴权阶段从 access token 解析出来的 organization_id 偏好（可被 X-Organization-Id 覆盖）
    preferred_organization_id: str | None = None


bearer_scheme = HTTPBearer(auto_error=True, description="Bearer JWT access token")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUser:
    """解析 Bearer access token 并返回当前用户。"""
    payload = decode_token(credentials.credentials, expected_type="access")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_repo = UserRepository(session)
    user: User | None = await user_repo.get(user_id)
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user_inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        platform_role=user.platform_role,
        status=user.status,
        preferred_organization_id=payload.get("organization_id"),
    )
