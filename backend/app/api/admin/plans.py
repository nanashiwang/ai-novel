from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_permission, require_platform_admin
from app.models.common import new_id
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.repositories import AuditLogRepository
from app.schemas.common import APIModel

router = APIRouter(prefix="/admin/plans", tags=["admin-plans"])


class AdminPlanFeatureResponse(APIModel):
    id: str
    feature_key: str
    enabled: bool
    limit_value: int | None = None
    limit_unit: str


class AdminPlanResponse(APIModel):
    id: str
    code: str
    name: str
    description: str
    price_monthly: float
    price_yearly: float | None = None
    currency: str
    status: str
    organization_count: int = 0
    features: list[AdminPlanFeatureResponse]


class AdminPlanFeatureInput(APIModel):
    feature_key: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    limit_value: int | None = Field(default=None, ge=0)
    limit_unit: str = Field(default="times", min_length=1, max_length=32)

    @field_validator("feature_key", "limit_unit")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("required")
        return stripped


class AdminPlanUpsertRequest(APIModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    price_monthly: float = Field(default=0, ge=0)
    price_yearly: float | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", min_length=1, max_length=8)
    status: str = Field(default="active", min_length=1, max_length=32)
    features: list[AdminPlanFeatureInput] = Field(default_factory=list)

    @field_validator("code", "name", "currency", "status")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("required")
        return stripped

    @field_validator("description")
    @classmethod
    def strip_optional_text(cls, value: str) -> str:
        return value.strip()


async def _plan_to_response(db: DbDep, plan: Plan) -> AdminPlanResponse:
    result = await db.execute(
        select(PlanFeature)
        .where(PlanFeature.plan_id == plan.id)
        .order_by(PlanFeature.feature_key.asc())
    )
    features = list(result.scalars().all())
    # 该 plan 当前被多少组织引用（plan_code 而非 id）
    count_stmt = select(func.count(Organization.id)).where(Organization.plan_code == plan.code)
    org_count = (await db.execute(count_stmt)).scalar_one() or 0
    return AdminPlanResponse(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        price_monthly=float(plan.price_monthly or 0),
        price_yearly=float(plan.price_yearly) if plan.price_yearly is not None else None,
        currency=plan.currency,
        status=plan.status,
        organization_count=int(org_count),
        features=[
            AdminPlanFeatureResponse(
                id=feature.id,
                feature_key=feature.feature_key,
                enabled=feature.enabled,
                limit_value=feature.limit_value,
                limit_unit=feature.limit_unit,
            )
            for feature in features
        ],
    )


async def _plan_features_snapshot(db: DbDep, plan_id: str) -> list[dict]:
    result = await db.execute(
        select(PlanFeature)
        .where(PlanFeature.plan_id == plan_id)
        .order_by(PlanFeature.feature_key.asc())
    )
    return [
        {
            "feature_key": feature.feature_key,
            "enabled": feature.enabled,
            "limit_value": feature.limit_value,
            "limit_unit": feature.limit_unit,
        }
        for feature in result.scalars().all()
    ]


async def _plan_audit_snapshot(db: DbDep, plan: Plan) -> dict:
    return {
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "price_monthly": float(plan.price_monthly or 0),
        "price_yearly": float(plan.price_yearly) if plan.price_yearly is not None else None,
        "currency": plan.currency,
        "status": plan.status,
        "features": await _plan_features_snapshot(db, plan.id),
    }


@router.get("", response_model=list[AdminPlanResponse])
async def list_admin_plans(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    result = await db.execute(select(Plan).order_by(Plan.price_monthly.asc(), Plan.code.asc()))
    plans = list(result.scalars().all())
    return [await _plan_to_response(db, plan) for plan in plans]


@router.post("", response_model=AdminPlanResponse, status_code=201)
async def create_admin_plan(
    payload: AdminPlanUpsertRequest,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "admin:plan:update")
    existing = await db.execute(select(Plan).where(Plan.code == payload.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="plan_code_exists")

    plan = Plan(
        id=new_id("plan"),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        price_monthly=Decimal(str(payload.price_monthly)),
        price_yearly=Decimal(str(payload.price_yearly)) if payload.price_yearly is not None else None,
        currency=payload.currency,
        status=payload.status,
    )
    db.add(plan)
    await db.flush()
    await _replace_features(db, plan.id, payload.features)
    after = await _plan_audit_snapshot(db, plan)
    await AuditLogRepository(db).create(
        organization_id=user.preferred_organization_id or "platform",
        actor_user_id=user.id,
        action="plan.create",
        target_type="plan",
        target_id=plan.id,
        before_data=None,
        after_data=after,
    )
    await db.commit()
    return await _plan_to_response(db, plan)


@router.put("/{plan_id}", response_model=AdminPlanResponse)
async def update_admin_plan(
    plan_id: str,
    payload: AdminPlanUpsertRequest,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "admin:plan:update")
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan_not_found")

    existing = await db.execute(select(Plan).where(Plan.code == payload.code, Plan.id != plan_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="plan_code_exists")

    before = await _plan_audit_snapshot(db, plan)
    plan.code = payload.code
    plan.name = payload.name
    plan.description = payload.description
    plan.price_monthly = Decimal(str(payload.price_monthly))
    plan.price_yearly = Decimal(str(payload.price_yearly)) if payload.price_yearly is not None else None
    plan.currency = payload.currency
    plan.status = payload.status
    await _replace_features(db, plan.id, payload.features)
    after = await _plan_audit_snapshot(db, plan)
    await AuditLogRepository(db).create(
        organization_id=user.preferred_organization_id or "platform",
        actor_user_id=user.id,
        action="plan.update",
        target_type="plan",
        target_id=plan_id,
        before_data=before,
        after_data=after,
    )
    await db.commit()
    return await _plan_to_response(db, plan)


async def _replace_features(
    db: DbDep,
    plan_id: str,
    features: list[AdminPlanFeatureInput],
) -> None:
    existing = await db.execute(select(PlanFeature).where(PlanFeature.plan_id == plan_id))
    for feature in existing.scalars().all():
        await db.delete(feature)
    await db.flush()

    seen: set[str] = set()
    for feature in features:
        if feature.feature_key in seen:
            raise HTTPException(status_code=400, detail="duplicate_feature_key")
        seen.add(feature.feature_key)
        db.add(
            PlanFeature(
                id=new_id("pf"),
                plan_id=plan_id,
                feature_key=feature.feature_key,
                enabled=feature.enabled,
                limit_value=feature.limit_value,
                limit_unit=feature.limit_unit,
            )
        )
    await db.flush()


@router.delete("/{plan_id}", status_code=204)
async def delete_admin_plan(
    plan_id: str,
    user: CurrentUserDep,
    db: DbDep,
):
    """删除套餐。

    引用保护：若仍有 organization 引用此 plan_code，返回 409 plan_in_use，
    避免运营误删导致组织额度初始化时找不到 limit_value 全部 402。
    """
    require_permission(user, "admin:plan:update")
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan_not_found")

    count_stmt = select(func.count(Organization.id)).where(Organization.plan_code == plan.code)
    org_count = int((await db.execute(count_stmt)).scalar_one() or 0)
    if org_count > 0:
        raise HTTPException(
            status_code=409,
            detail="plan_in_use",
        )

    before = await _plan_audit_snapshot(db, plan)
    # 先删 features，再删 plan（避免外键残留）
    features = await db.execute(select(PlanFeature).where(PlanFeature.plan_id == plan_id))
    for feature in features.scalars().all():
        await db.delete(feature)
    await db.flush()

    await AuditLogRepository(db).create(
        organization_id=user.preferred_organization_id or "platform",
        actor_user_id=user.id,
        action="plan.delete",
        target_type="plan",
        target_id=plan_id,
        before_data=before,
        after_data=None,
    )
    await db.delete(plan)
    await db.commit()
