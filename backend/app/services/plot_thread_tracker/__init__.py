"""PlotThread Revision Tracker。

Sprint 12-C：剧情线（主线 / 副线 / 伏笔）演进的状态机。结构与 world_tracker
完全对称，仅字段白名单 + 默认 reason 文案不同。

字段白名单：
    title / thread_type / description / status

不包含：
    - related_characters：列表，AI 反推容易越权；通过 copilot 提案处理。
    - opened_at_scene_id / closed_at_scene_id：内部状态，不是创作字段。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot_thread import PlotThread
from app.models.plot_thread_revision import PlotThreadRevision
from app.repositories import PlotThreadRepository, PlotThreadRevisionRepository

PLOT_THREAD_TRACKABLE_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "thread_type",
        "description",
        "status",
        "expected_resolve_chapter",
    }
)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _changed(old: Any, new: Any) -> bool:
    return _normalize_value(old) != _normalize_value(new)


async def _supersede_prior_applied(
    session: AsyncSession,
    *,
    organization_id: str,
    item_id: str,
    field: str,
    exclude_id: str | None = None,
) -> int:
    stmt = select(PlotThreadRevision).where(
        PlotThreadRevision.organization_id == organization_id,
        PlotThreadRevision.item_id == item_id,
        PlotThreadRevision.field == field,
        PlotThreadRevision.status == "applied",
    )
    if exclude_id is not None:
        stmt = stmt.where(PlotThreadRevision.id != exclude_id)
    rows = list((await session.execute(stmt)).scalars().all())
    for row in rows:
        row.status = "superseded"
    return len(rows)


async def record_user_edit(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    item: PlotThread,
    field: str,
    new_value: Any,
    user_id: str,
    reason: str = "",
) -> PlotThreadRevision | None:
    if field not in PLOT_THREAD_TRACKABLE_FIELDS:
        return None
    old_value = getattr(item, field, None)
    if not _changed(old_value, new_value):
        return None

    now = datetime.now(timezone.utc)
    revision = await PlotThreadRevisionRepository(session).create(
        organization_id=organization_id,
        project_id=project_id,
        item_id=item.id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        source="user_edit",
        scene_id=None,
        status="applied",
        created_by=user_id,
        applied_by=user_id,
        applied_at=now,
    )
    await _supersede_prior_applied(
        session,
        organization_id=organization_id,
        item_id=item.id,
        field=field,
        exclude_id=revision.id,
    )
    setattr(item, field, new_value)
    return revision


async def record_ai_inferred(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    item: PlotThread,
    field: str,
    new_value: Any,
    reason: str,
    scene_id: str | None = None,
) -> PlotThreadRevision | None:
    if field not in PLOT_THREAD_TRACKABLE_FIELDS:
        return None
    old_value = getattr(item, field, None)
    if not _changed(old_value, new_value):
        return None
    return await PlotThreadRevisionRepository(session).create(
        organization_id=organization_id,
        project_id=project_id,
        item_id=item.id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        reason=reason or "AI 推演",
        source="ai_inferred",
        scene_id=scene_id,
        status="pending",
        created_by=None,
        applied_by=None,
        applied_at=None,
    )


async def record_copilot_proposal(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    item: PlotThread,
    field: str,
    new_value: Any,
    reason: str,
    user_id: str | None,
) -> PlotThreadRevision | None:
    if field not in PLOT_THREAD_TRACKABLE_FIELDS:
        return None
    old_value = getattr(item, field, None)
    if not _changed(old_value, new_value):
        return None
    return await PlotThreadRevisionRepository(session).create(
        organization_id=organization_id,
        project_id=project_id,
        item_id=item.id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        reason=reason or "AI 共创提案",
        source="copilot",
        scene_id=None,
        status="pending",
        created_by=user_id,
        applied_by=None,
        applied_at=None,
    )


async def apply_revision(
    session: AsyncSession,
    *,
    organization_id: str,
    revision: PlotThreadRevision,
    user_id: str,
) -> PlotThread | None:
    if revision.status != "pending":
        return None
    item = await PlotThreadRepository(session).get(
        revision.item_id, organization_id=organization_id
    )
    if not item:
        return None
    if revision.field in PLOT_THREAD_TRACKABLE_FIELDS:
        setattr(item, revision.field, revision.new_value)
    now = datetime.now(timezone.utc)
    revision.status = "applied"
    revision.applied_by = user_id
    revision.applied_at = now
    await _supersede_prior_applied(
        session,
        organization_id=organization_id,
        item_id=item.id,
        field=revision.field,
        exclude_id=revision.id,
    )
    return item


async def reject_revision(
    session: AsyncSession,
    *,
    revision: PlotThreadRevision,
    user_id: str,
) -> PlotThreadRevision | None:
    if revision.status != "pending":
        return None
    revision.status = "rejected"
    revision.applied_by = user_id
    revision.applied_at = datetime.now(timezone.utc)
    return revision


async def rollback_to(
    session: AsyncSession,
    *,
    organization_id: str,
    revision: PlotThreadRevision,
    user_id: str,
) -> PlotThread | None:
    item = await PlotThreadRepository(session).get(
        revision.item_id, organization_id=organization_id
    )
    if not item:
        return None
    if revision.field not in PLOT_THREAD_TRACKABLE_FIELDS:
        return None
    target_value = revision.new_value
    now = datetime.now(timezone.utc)
    new_rev = await PlotThreadRevisionRepository(session).create(
        organization_id=organization_id,
        project_id=revision.project_id,
        item_id=item.id,
        field=revision.field,
        old_value=getattr(item, revision.field, None),
        new_value=target_value,
        reason=f"rollback to {revision.id}",
        source="user_edit",
        scene_id=None,
        status="applied",
        created_by=user_id,
        applied_by=user_id,
        applied_at=now,
    )
    setattr(item, revision.field, target_value)
    await _supersede_prior_applied(
        session,
        organization_id=organization_id,
        item_id=item.id,
        field=revision.field,
        exclude_id=new_rev.id,
    )
    return item


async def list_revisions(
    session: AsyncSession,
    *,
    organization_id: str,
    item_id: str,
    status: str | None = None,
    limit: int = 100,
) -> list[PlotThreadRevision]:
    stmt = (
        select(PlotThreadRevision)
        .where(
            PlotThreadRevision.organization_id == organization_id,
            PlotThreadRevision.item_id == item_id,
        )
        .order_by(desc(PlotThreadRevision.created_at))
        .limit(limit)
    )
    if status:
        stmt = stmt.where(PlotThreadRevision.status == status)
    return list((await session.execute(stmt)).scalars().all())


async def count_pending_for_project(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
) -> int:
    from sqlalchemy import func as _func

    stmt = select(_func.count(PlotThreadRevision.id)).where(
        PlotThreadRevision.organization_id == organization_id,
        PlotThreadRevision.project_id == project_id,
        PlotThreadRevision.status == "pending",
    )
    return int((await session.execute(stmt)).scalar_one())


async def count_pending_by_item(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
) -> dict[str, int]:
    from sqlalchemy import func as _func

    stmt = (
        select(PlotThreadRevision.item_id, _func.count(PlotThreadRevision.id))
        .where(
            PlotThreadRevision.organization_id == organization_id,
            PlotThreadRevision.project_id == project_id,
            PlotThreadRevision.status == "pending",
        )
        .group_by(PlotThreadRevision.item_id)
    )
    rows = (await session.execute(stmt)).all()
    return {item_id: int(count) for item_id, count in rows}
