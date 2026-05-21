"""信息释放 ledger API（Sprint 14-C5）。

提供 CRUD + status 切换。所有路由都按 project 作用域，与 plot_threads /
world_items 等其它 Bible 子资源对齐。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import InformationLedgerRepository
from app.schemas.information_ledger import (
    LedgerCreate,
    LedgerResponse,
    LedgerStatusUpdate,
    LedgerUpdate,
)

router = APIRouter(
    prefix="/projects/{project_id}/information-ledger",
    tags=["information-ledger"],
)


@router.get("", response_model=list[LedgerResponse])
async def list_ledger_entries(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    rows = await InformationLedgerRepository(db).list(
        organization_id=tenant.organization_id, project_id=project_id
    )
    return rows


@router.post("", response_model=LedgerResponse, status_code=201)
async def create_ledger_entry(
    project_id: str,
    payload: LedgerCreate,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    entry = await InformationLedgerRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return entry


@router.patch("/{entry_id}", response_model=LedgerResponse)
async def update_ledger_entry(
    project_id: str,
    entry_id: str,
    payload: LedgerUpdate,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    repo = InformationLedgerRepository(db)
    entry = await repo.get(entry_id, organization_id=tenant.organization_id)
    if not entry or entry.project_id != project_id:
        raise NotFoundError(
            "information_ledger_not_found", code="information_ledger_not_found"
        )
    patch = payload.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(entry, key, value)
    await db.flush()
    await db.commit()
    return entry


@router.patch("/{entry_id}/status", response_model=LedgerResponse)
async def toggle_ledger_status(
    project_id: str,
    entry_id: str,
    payload: LedgerStatusUpdate,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """快捷切换 secret → partial → public 的状态。

    与通用 PATCH 等价，但单独留一个路由让前端 UI 可以做"一键公开"操作，
    无需构造完整 update payload。
    """
    require_permission(user, "project:update", tenant)
    repo = InformationLedgerRepository(db)
    entry = await repo.get(entry_id, organization_id=tenant.organization_id)
    if not entry or entry.project_id != project_id:
        raise NotFoundError(
            "information_ledger_not_found", code="information_ledger_not_found"
        )
    entry.status = payload.status
    await db.flush()
    await db.commit()
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_ledger_entry(
    project_id: str,
    entry_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    repo = InformationLedgerRepository(db)
    entry = await repo.get(entry_id, organization_id=tenant.organization_id)
    if not entry or entry.project_id != project_id:
        raise NotFoundError(
            "information_ledger_not_found", code="information_ledger_not_found"
        )
    await repo.delete(entry_id, organization_id=tenant.organization_id)
    await db.commit()
