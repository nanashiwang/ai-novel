"""平台管理员：组织管理。

提供：
- GET    /admin/organizations               所有组织列表
- PATCH  /admin/organizations/{id}          修改组织套餐 / 状态（写 audit + 自动同步 quota_balance）
- GET    /admin/organizations/{id}/quotas   该组织所有 quota_balance
- PATCH  /admin/organizations/{id}/quota    手动调整某 quota 的 limit
- GET    /admin/quota-balances              跨组织 quota 列表（可按 org / quota_key 过滤）
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import Field, field_validator
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DbDep
from app.core.exceptions import AppError, NotFoundError
from app.core.permissions import require_permission, require_platform_admin
from app.models.plan import Plan
from app.repositories import (
    AuditLogRepository,
    OrganizationRepository,
    QuotaBalanceRepository,
)
from app.schemas.common import APIModel
from app.services.quota.service import quota_service

router = APIRouter(prefix="/admin", tags=["admin-organizations"])


class AdminOrgResponse(APIModel):
    id: str
    name: str
    type: str
    plan_code: str
    status: str
    owner_user_id: str


class AdminOrgUpdateRequest(APIModel):
    plan_code: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=32)
    reason: str = Field(default="", max_length=200)

    @field_validator("plan_code", "status")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class AdjustQuotaRequest(APIModel):
    quota_key: str
    delta: int
    reason: str = ""


class QuotaBalanceResponse(APIModel):
    id: str
    organization_id: str
    quota_key: str
    limit_value: int
    used_value: int
    reserved_value: int
    period_start: str | None = None
    period_end: str | None = None


def _balance_to_response(balance) -> QuotaBalanceResponse:  # noqa: ANN001
    return QuotaBalanceResponse(
        id=balance.id,
        organization_id=balance.organization_id,
        quota_key=balance.quota_key,
        limit_value=balance.limit_value,
        used_value=balance.used_value,
        reserved_value=balance.reserved_value,
        period_start=balance.period_start.isoformat() if balance.period_start else None,
        period_end=balance.period_end.isoformat() if balance.period_end else None,
    )


@router.get("/organizations", response_model=list[AdminOrgResponse])
async def organizations(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    rows = await OrganizationRepository(db).list(limit=200)
    return rows


@router.patch("/organizations/{organization_id}", response_model=AdminOrgResponse)
async def update_organization(
    organization_id: str,
    payload: AdminOrgUpdateRequest,
    user: CurrentUserDep,
    db: DbDep,
):
    """修改组织套餐 / 状态。

    切换 plan_code 后自动按新 plan_features 重置 quota_balance.limit_value，
    used_value / reserved_value 保留（升级不清零、降级不退款）。所有改动写
    admin_audit_log。
    """
    require_permission(user, "admin:organization:update")
    org_repo = OrganizationRepository(db)
    org = await org_repo.get(organization_id)
    if not org:
        raise NotFoundError("organization_not_found")

    if payload.plan_code is None and payload.status is None:
        raise AppError("validation_error", code="validation_error")

    before = {"plan_code": org.plan_code, "status": org.status}
    quota_sync_result: dict | None = None

    if payload.plan_code is not None and payload.plan_code != org.plan_code:
        # 目标 plan 必须存在且 active，避免切到不存在的套餐导致额度全空
        plan_stmt = select(Plan).where(Plan.code == payload.plan_code)
        plan = (await db.execute(plan_stmt)).scalar_one_or_none()
        if not plan:
            raise NotFoundError("plan_not_found", code="plan_not_found")
        if plan.status != "active":
            raise AppError("plan_inactive", code="plan_inactive")

        org.plan_code = payload.plan_code
        quota_sync_result = await quota_service.sync_to_plan(
            db,
            organization_id=organization_id,
            plan_code=payload.plan_code,
        )

    if payload.status is not None and payload.status != org.status:
        org.status = payload.status

    after = {"plan_code": org.plan_code, "status": org.status}
    audit_payload: dict = {"before": before, "after": after, "reason": payload.reason}
    if quota_sync_result is not None:
        audit_payload["quota_sync"] = quota_sync_result

    await AuditLogRepository(db).create(
        organization_id=organization_id,
        actor_user_id=user.id,
        action="organization.update",
        target_type="organization",
        target_id=organization_id,
        before_data=before,
        after_data=audit_payload,
    )
    await db.commit()
    return org


@router.get(
    "/organizations/{organization_id}/quotas",
    response_model=list[QuotaBalanceResponse],
)
async def organization_quotas(
    organization_id: str,
    user: CurrentUserDep,
    db: DbDep,
):
    require_platform_admin(user)
    rows = await QuotaBalanceRepository(db).list(organization_id=organization_id)
    return [_balance_to_response(b) for b in rows]


@router.patch("/organizations/{organization_id}/quota")
async def adjust_quota(
    organization_id: str,
    payload: AdjustQuotaRequest,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "admin:quota:update")
    balance = await QuotaBalanceRepository(db).get_for_update(
        organization_id=organization_id,
        quota_key=payload.quota_key,
    )
    if not balance:
        raise NotFoundError("quota_not_found")
    before = balance.limit_value
    balance.limit_value = max(0, balance.limit_value + payload.delta)

    audit = await AuditLogRepository(db).create(
        organization_id=organization_id,
        actor_user_id=user.id,
        action="quota.manual_adjust",
        target_type="quota_balance",
        target_id=balance.id,
        before_data={"limit_value": before},
        after_data={"limit_value": balance.limit_value, "reason": payload.reason},
    )
    await db.commit()
    return {
        "status": "adjusted",
        "audit_log_id": audit.id,
        "limit_value": balance.limit_value,
    }


@router.get("/quota-balances", response_model=list[QuotaBalanceResponse])
async def quota_balances(
    user: CurrentUserDep,
    db: DbDep,
    organization_id: str | None = Query(default=None),
    quota_key: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """跨组织 quota 列表，支持过滤。

    AdminQuotasPage 之前只能通过 /quotas（用户视角）拿当前用户组织的 balance，
    无法跨租户审计。本接口在 platform admin 范围内放开过滤维度。
    """
    require_platform_admin(user)
    rows = await QuotaBalanceRepository(db).list(
        limit=limit,
        organization_id=organization_id,
        quota_key=quota_key,
    )
    return [_balance_to_response(b) for b in rows]


@router.get("/quota-keys")
async def list_quota_keys(user: CurrentUserDep, db: DbDep):
    """返回已注册的 quota_key 列表 + 出现频次，供前端套餐编辑下拉使用。

    数据来源：plan_features 实际出现过的 feature_key（含已禁用），合并去重后
    按使用次数排序。前端拿来当 datalist / suggestion 使用，避免硬编码。
    """
    require_platform_admin(user)
    # 从 plan_features 聚合 distinct feature_key + 计数
    from app.models.plan import PlanFeature  # noqa: PLC0415

    stmt = (
        select(PlanFeature.feature_key, func.count(PlanFeature.id))
        .group_by(PlanFeature.feature_key)
        .order_by(func.count(PlanFeature.id).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [{"feature_key": key, "used_in_plans": count} for key, count in rows]
