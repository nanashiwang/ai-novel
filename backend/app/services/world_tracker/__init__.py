"""WorldItem Revision Tracker。

Sprint 12-C：镜像 character_tracker 的状态机，让世界观条目（地点 / 势力 / 硬规则）
也有完整的版本链 + AI 审核流程。

字段白名单（与 character_tracker 一样保持显式）：
    type / name / description / importance / is_hard_rule

不包含：
    - rules / related_characters / attributes：这些是结构化字典或外链 id 数组，
      AI 反推难度大且没有明确语义；通过 copilot 提案路径单独维护更安全。

状态机：
    pending → applied / rejected / superseded
    applied → superseded（被新 applied 替换）

source：
    - 'user_edit'   → 用户在前端 PATCH，直接落 applied
    - 'copilot'     → AI 设定共创对话的提案，pending；用户 apply 后落 applied
    - 'ai_inferred' → 模型从 scene 正文反推的字段变化，pending；强 evidence 约束
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.world_item import WorldItem
from app.models.world_item_revision import WorldItemRevision
from app.repositories import WorldItemRepository, WorldItemRevisionRepository

# 字段白名单：哪些 WorldItem 字段可以走 revision 链
WORLD_ITEM_TRACKABLE_FIELDS: frozenset[str] = frozenset(
    {
        "type",
        "name",
        "description",
        "importance",
        "is_hard_rule",
    }
)


def _normalize_value(value: Any) -> Any:
    """让 None / "" / False 等"空"值在比较时归一化，避免重复写 revision。"""
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
    """把同 item 同 field 的旧 applied revision 标为 superseded。"""
    stmt = (
        select(WorldItemRevision)
        .where(
            WorldItemRevision.organization_id == organization_id,
            WorldItemRevision.item_id == item_id,
            WorldItemRevision.field == field,
            WorldItemRevision.status == "applied",
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(WorldItemRevision.id != exclude_id)
    rows = list((await session.execute(stmt)).scalars().all())
    for row in rows:
        row.status = "superseded"
    return len(rows)


async def record_user_edit(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    item: WorldItem,
    field: str,
    new_value: Any,
    user_id: str,
    reason: str = "",
) -> WorldItemRevision | None:
    """记录一次用户手动编辑，直接落 applied 状态。

    - 仅追踪白名单字段；非白名单字段直接返回 None，不报错（调用方更宽容）。
    - 旧值与新值归一化相等时也返回 None（避免空操作刷历史）。
    - 同字段的旧 applied 会被标为 superseded。
    """
    if field not in WORLD_ITEM_TRACKABLE_FIELDS:
        return None
    old_value = getattr(item, field, None)
    if not _changed(old_value, new_value):
        return None

    now = datetime.now(timezone.utc)
    revision = await WorldItemRevisionRepository(session).create(
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
    item: WorldItem,
    field: str,
    new_value: Any,
    reason: str,
    scene_id: str | None = None,
) -> WorldItemRevision | None:
    """AI 从 scene 正文反推字段变化，落 pending；等用户 apply 才生效。"""
    if field not in WORLD_ITEM_TRACKABLE_FIELDS:
        return None
    old_value = getattr(item, field, None)
    if not _changed(old_value, new_value):
        return None
    return await WorldItemRevisionRepository(session).create(
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
    item: WorldItem,
    field: str,
    new_value: Any,
    reason: str,
    user_id: str | None,
) -> WorldItemRevision | None:
    """AI 设定共创对话的字段级提案，落 pending；与 ai_inferred 区分 source。"""
    if field not in WORLD_ITEM_TRACKABLE_FIELDS:
        return None
    old_value = getattr(item, field, None)
    if not _changed(old_value, new_value):
        return None
    return await WorldItemRevisionRepository(session).create(
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
    revision: WorldItemRevision,
    user_id: str,
) -> WorldItem | None:
    """把 pending revision 推到 applied，并把 item 字段写到 new_value。"""
    if revision.status != "pending":
        return None
    item = await WorldItemRepository(session).get(
        revision.item_id, organization_id=organization_id
    )
    if not item:
        return None
    if revision.field in WORLD_ITEM_TRACKABLE_FIELDS:
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
    revision: WorldItemRevision,
    user_id: str,
) -> WorldItemRevision | None:
    """显式拒绝一条 pending revision；rejected 状态不再 supersede 历史。"""
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
    revision: WorldItemRevision,
    user_id: str,
) -> WorldItem | None:
    """把 item 字段回滚到某条历史 revision 的 new_value。

    回滚本身会写一条新的 applied revision，把 reason 设成 "rollback to <id>"，
    保留可审计的链路。
    """
    item = await WorldItemRepository(session).get(
        revision.item_id, organization_id=organization_id
    )
    if not item:
        return None
    if revision.field not in WORLD_ITEM_TRACKABLE_FIELDS:
        return None
    target_value = revision.new_value
    now = datetime.now(timezone.utc)
    new_rev = await WorldItemRevisionRepository(session).create(
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
) -> list[WorldItemRevision]:
    stmt = (
        select(WorldItemRevision)
        .where(
            WorldItemRevision.organization_id == organization_id,
            WorldItemRevision.item_id == item_id,
        )
        .order_by(desc(WorldItemRevision.created_at))
        .limit(limit)
    )
    if status:
        stmt = stmt.where(WorldItemRevision.status == status)
    return list((await session.execute(stmt)).scalars().all())


async def count_pending_for_project(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
) -> int:
    from sqlalchemy import func as _func

    stmt = select(_func.count(WorldItemRevision.id)).where(
        WorldItemRevision.organization_id == organization_id,
        WorldItemRevision.project_id == project_id,
        WorldItemRevision.status == "pending",
    )
    return int((await session.execute(stmt)).scalar_one())


async def count_pending_by_item(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
) -> dict[str, int]:
    """按 item_id 聚合 pending 数，给前端列表卡片角标用。"""
    from sqlalchemy import func as _func

    stmt = (
        select(WorldItemRevision.item_id, _func.count(WorldItemRevision.id))
        .where(
            WorldItemRevision.organization_id == organization_id,
            WorldItemRevision.project_id == project_id,
            WorldItemRevision.status == "pending",
        )
        .group_by(WorldItemRevision.item_id)
    )
    rows = (await session.execute(stmt)).all()
    return {item_id: int(count) for item_id, count in rows}
