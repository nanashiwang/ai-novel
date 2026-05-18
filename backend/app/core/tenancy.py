"""租户上下文解析。

请求带 `X-Organization-Id` 头时优先使用；否则使用 access token 中
的 preferred_organization_id 或用户的默认个人组织。所有上下文均通过 DB 校验。

平台管理员可跨租户访问，但会写入 admin_audit_logs 留痕。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import CurrentUser, get_current_user
from app.models.audit_log import AdminAuditLog
from app.models.common import new_id
from app.models.organization import Organization, OrganizationMember

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TenantContext:
    organization_id: str
    organization_name: str
    plan_code: str
    organization_role: str
    status: str = "active"


async def resolve_tenant(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_organization_id: str | None = Header(default=None, alias="X-Organization-Id"),
) -> TenantContext:
    organization_id = x_organization_id or current_user.preferred_organization_id

    if not organization_id:
        # 兜底：使用用户加入的第一个组织
        member = (
            await session.execute(
                select(OrganizationMember)
                .where(
                    OrganizationMember.user_id == current_user.id,
                    OrganizationMember.status == "active",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="no_organization",
            )
        organization_id = member.organization_id
        member_role = member.role
        is_admin_crossing = False
    else:
        member_stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.status == "active",
        )
        member = (await session.execute(member_stmt)).scalar_one_or_none()
        if member:
            member_role = member.role
            is_admin_crossing = False
        else:
            # 非成员：仅平台管理员可跨租户访问
            if current_user.platform_role not in {"admin", "super_admin"}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="tenant_not_allowed",
                )
            member_role = "owner"
            is_admin_crossing = True

    org = (
        await session.execute(select(Organization).where(Organization.id == organization_id))
    ).scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="organization_not_found",
        )

    # 平台管理员跨租户：写审计日志（best-effort，不阻断请求）
    if is_admin_crossing:
        try:
            session.add(
                AdminAuditLog(
                    id=new_id("audit"),
                    organization_id=organization_id,
                    actor_user_id=current_user.id,
                    action="tenant.cross_access",
                    target_type="organization",
                    target_id=organization_id,
                    after_data={
                        "platform_role": current_user.platform_role,
                        "path": request.url.path,
                        "method": request.method,
                    },
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("User-Agent"),
                )
            )
            await session.flush()
        except Exception:  # noqa: BLE001
            _logger.exception("failed_to_write_cross_tenant_audit")

    return TenantContext(
        organization_id=org.id,
        organization_name=org.name,
        plan_code=org.plan_code,
        organization_role=member_role,
        status=org.status,
    )


def ensure_same_tenant(resource_organization_id: str, tenant: TenantContext) -> None:
    if resource_organization_id != tenant.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource_not_found")
