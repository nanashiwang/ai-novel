from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from .security import CurrentUser


@dataclass(frozen=True)
class TenantContext:
    organization_id: str
    organization_name: str
    plan_code: str
    status: str = "active"


async def resolve_tenant(
    current_user: CurrentUser,
    x_organization_id: str | None = "org_personal",
) -> TenantContext:
    organization_id = x_organization_id or "org_personal"
    if (
        organization_id != "org_personal"
        and current_user.platform_role not in {"admin", "super_admin"}
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant_not_allowed")
    return TenantContext(
        organization_id=organization_id,
        organization_name="personal-workspace",
        plan_code="Pro",
    )


def ensure_same_tenant(resource_organization_id: str, tenant: TenantContext) -> None:
    if resource_organization_id != tenant.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource_not_found")
