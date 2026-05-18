"""权限校验。

ROLE_PERMISSIONS：组织内角色（owner / editor / viewer / billing_manager）的权限集合
ADMIN_PERMISSIONS / SUPER_ADMIN_PERMISSIONS：平台层权限

CurrentUser 仅承载 platform_role；组织内角色通过 TenantContext.organization_role 传入。
"""
from __future__ import annotations

from fastapi import HTTPException, status

from .security import CurrentUser
from .tenancy import TenantContext

PLATFORM_ADMIN_ROLES = {"admin", "super_admin"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "project:read",
        "project:create",
        "project:update",
        "project:delete",
        "character:read",
        "character:write",
        "chapter:read",
        "chapter:write",
        "scene:read",
        "scene:write",
        "memory:read",
        "memory:write",
        "generation_job:create",
        "generation_job:cancel",
        "export:create",
        "billing:read",
        "billing:manage",
        "organization:manage",
    },
    "editor": {
        "project:read",
        "project:update",
        "character:read",
        "character:write",
        "chapter:read",
        "chapter:write",
        "scene:read",
        "scene:write",
        "memory:read",
        "memory:write",
        "generation_job:create",
        "export:create",
    },
    "viewer": {
        "project:read",
        "character:read",
        "chapter:read",
        "scene:read",
        "memory:read",
    },
    "billing_manager": {
        "billing:read",
        "billing:manage",
    },
}

ADMIN_PERMISSIONS = {
    "admin:user:read",
    "admin:user:update",
    "admin:organization:read",
    "admin:organization:update",
    "admin:generation_job:read",
    "admin:generation_job:cancel",
    "admin:model_call:read",
    "admin:audit_log:read",
    "admin:content_review:read",
}

SUPER_ADMIN_PERMISSIONS = ADMIN_PERMISSIONS | {
    "admin:system:update",
    "admin:quota:update",
    "admin:plan:update",
    "admin:user:delete",
}


def is_platform_admin(user: CurrentUser) -> bool:
    return user.platform_role in PLATFORM_ADMIN_ROLES


def _collect_permissions(user: CurrentUser, tenant: TenantContext | None) -> set[str]:
    permissions: set[str] = set()
    if tenant:
        permissions |= ROLE_PERMISSIONS.get(tenant.organization_role, set())
    if user.platform_role == "admin":
        permissions |= ADMIN_PERMISSIONS
    if user.platform_role == "super_admin":
        permissions |= SUPER_ADMIN_PERMISSIONS
    return permissions


def require_permission(
    user: CurrentUser,
    permission: str,
    tenant: TenantContext | None = None,
) -> None:
    """统一权限校验。

    传入 tenant 时使用组织内角色 + 平台角色合并集合判定；
    未传入 tenant 时仅看平台角色（用于 /admin/* 接口）。
    """
    permissions = _collect_permissions(user, tenant)
    if permission not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission_denied")


def require_platform_admin(user: CurrentUser) -> None:
    if not is_platform_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
