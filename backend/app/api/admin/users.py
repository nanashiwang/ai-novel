"""平台管理员：用户管理。

提供：
- GET    /admin/users                            用户列表（已有）
- GET    /admin/users/{user_id}                  用户详情 + 所属组织
- PATCH  /admin/users/{user_id}                  改 status / platform_role / display_name
- POST   /admin/users/{user_id}/reset-password   重置密码（返回临时密码）

约束：
- 不能修改自己的 role / status，避免误把自己从 super_admin 降级
- 操作全部写入 admin_audit_log
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter
from pydantic import Field, field_validator
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.core.exceptions import AppError, NotFoundError
from app.core.passwords import hash_password
from app.core.permissions import (
    PLATFORM_ADMIN_ROLES,
    is_platform_admin,
    require_permission,
    require_platform_admin,
)
from app.models.organization import Organization, OrganizationMember
from app.repositories import AuditLogRepository, UserRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

# 允许平台 admin 设置的角色集合；user / admin / super_admin 三档
ALLOWED_PLATFORM_ROLES = {"user", "admin", "super_admin"}
ALLOWED_USER_STATUSES = {"active", "disabled"}


class AdminUserResponse(APIModel):
    id: str
    email: str
    display_name: str
    platform_role: str
    status: str


class AdminUserOrgInfo(APIModel):
    organization_id: str
    organization_name: str
    plan_code: str
    role: str
    member_status: str


class AdminUserDetailResponse(AdminUserResponse):
    is_platform_staff: bool
    organizations: list[AdminUserOrgInfo]


class AdminUserUpdateRequest(APIModel):
    display_name: str | None = Field(default=None, max_length=120)
    platform_role: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=32)
    reason: str = Field(default="", max_length=200)

    @field_validator("display_name", "platform_role", "status")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ResetPasswordResponse(APIModel):
    temp_password: str
    note: str = "请通过安全渠道告知用户并提示首次登录后修改密码。"


@router.get("", response_model=list[AdminUserResponse])
async def list_users(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    rows = await UserRepository(db).list(limit=200)
    return rows


@router.get("/{user_id}", response_model=AdminUserDetailResponse)
async def get_user(user_id: str, user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    target = await UserRepository(db).get(user_id)
    if not target:
        raise NotFoundError("user_not_found", code="user_not_found")
    # 拉所属组织 + 角色
    stmt = (
        select(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    organizations = [
        AdminUserOrgInfo(
            organization_id=org.id,
            organization_name=org.name,
            plan_code=org.plan_code,
            role=member.role,
            member_status=member.status,
        )
        for member, org in rows
    ]
    return AdminUserDetailResponse(
        id=target.id,
        email=target.email,
        display_name=target.display_name,
        platform_role=target.platform_role,
        status=target.status,
        is_platform_staff=target.is_platform_staff,
        organizations=organizations,
    )


@router.patch("/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "admin:user:update")
    target = await UserRepository(db).get(user_id)
    if not target:
        raise NotFoundError("user_not_found", code="user_not_found")

    # 关键安全约束：不允许修改自己的 role / status，避免锁死系统
    if user_id == user.id and (
        payload.platform_role is not None or payload.status is not None
    ):
        raise AppError("cannot_modify_self", code="cannot_modify_self")

    if payload.platform_role is not None and payload.platform_role not in ALLOWED_PLATFORM_ROLES:
        raise AppError("invalid_role", code="invalid_role")
    # 仅 super_admin 可以把别人提升为 admin / super_admin
    if payload.platform_role in PLATFORM_ADMIN_ROLES and user.platform_role != "super_admin":
        raise AppError("permission_denied", code="permission_denied")
    if payload.status is not None and payload.status not in ALLOWED_USER_STATUSES:
        raise AppError("invalid_role", code="invalid_role")

    before = {
        "display_name": target.display_name,
        "platform_role": target.platform_role,
        "status": target.status,
    }
    if payload.display_name is not None:
        target.display_name = payload.display_name
    if payload.platform_role is not None:
        target.platform_role = payload.platform_role
        # is_platform_staff 与 platform_role 同步：admin/super_admin → True，user → False
        target.is_platform_staff = payload.platform_role in PLATFORM_ADMIN_ROLES
    if payload.status is not None:
        target.status = payload.status
    after = {
        "display_name": target.display_name,
        "platform_role": target.platform_role,
        "status": target.status,
    }

    await AuditLogRepository(db).create(
        organization_id=user.preferred_organization_id or "platform",
        actor_user_id=user.id,
        action="user.update",
        target_type="user",
        target_id=user_id,
        before_data=before,
        after_data={**after, "reason": payload.reason},
    )
    await db.commit()
    return target


@router.post(
    "/{user_id}/reset-password",
    response_model=ResetPasswordResponse,
    status_code=200,
)
async def reset_password(user_id: str, user: CurrentUserDep, db: DbDep):
    """强制重置密码。返回随机临时密码（仅本次响应返回，DB 只存哈希）。"""
    require_permission(user, "admin:user:update")
    target = await UserRepository(db).get(user_id)
    if not target:
        raise NotFoundError("user_not_found", code="user_not_found")

    # 16 字节 url-safe ≈ 22 字符，足够安全
    temp_password = secrets.token_urlsafe(12)
    target.password_hash = hash_password(temp_password)

    await AuditLogRepository(db).create(
        organization_id=user.preferred_organization_id or "platform",
        actor_user_id=user.id,
        action="user.reset_password",
        target_type="user",
        target_id=user_id,
        before_data=None,
        after_data={"reset_by": user.id},
    )
    await db.commit()
    return ResetPasswordResponse(temp_password=temp_password)


# 兜底确保 is_platform_admin 不会被未导入处误用
_ = is_platform_admin
