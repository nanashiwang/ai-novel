from __future__ import annotations

from fastapi import HTTPException, status

from .security import CurrentUser

PLATFORM_ADMIN_ROLES = {"admin", "super_admin"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "project:read",
        "project:create",
        "project:update",
        "generation_job:create",
        "generation_job:cancel",
        "billing:read",
    },
    "editor": {"project:read", "project:update", "generation_job:create"},
    "viewer": {"project:read"},
}

ADMIN_PERMISSIONS = {
    "admin:user:read",
    "admin:organization:read",
    "admin:generation_job:read",
    "admin:generation_job:cancel",
    "admin:model_call:read",
    "admin:audit_log:read",
}

SUPER_ADMIN_PERMISSIONS = ADMIN_PERMISSIONS | {
    "admin:system:update",
    "admin:quota:update",
    "admin:plan:update",
}


def is_platform_admin(user: CurrentUser) -> bool:
    return user.platform_role in PLATFORM_ADMIN_ROLES


def require_permission(user: CurrentUser, permission: str) -> None:
    permissions = set(ROLE_PERMISSIONS.get(user.organization_role, set()))
    if user.platform_role == "admin":
        permissions |= ADMIN_PERMISSIONS
    if user.platform_role == "super_admin":
        permissions |= SUPER_ADMIN_PERMISSIONS
    if permission not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission_denied")


def require_platform_admin(user: CurrentUser) -> None:
    if not is_platform_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
