from __future__ import annotations

from typing import Annotated
from fastapi import Depends, Header
from app.core.security import CurrentUser, get_current_user
from app.core.tenancy import TenantContext, resolve_tenant


async def tenant_dependency(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    x_organization_id: str | None = Header(default="org_personal", alias="X-Organization-Id"),
) -> TenantContext:
    return await resolve_tenant(user, x_organization_id)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
TenantDep = Annotated[TenantContext, Depends(tenant_dependency)]
