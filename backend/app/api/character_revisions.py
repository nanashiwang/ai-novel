"""人物字段版本链 API。

资源：`/api/v1/projects/{project_id}/characters/{character_id}/revisions`

- `GET /`              列出该人物所有 revision（按时间倒序）
- `POST /{rev}/apply`  应用一条 pending revision 到 character
- `POST /{rev}/reject` 标记 pending revision 为 rejected
- `POST /{rev}/rollback` 把某条历史 revision 重新 apply（用于回滚）
- `GET /pending/count`    返回当前 project 下所有 pending revisions 计数（按 character 分组）
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.models.chapter import Chapter
from app.models.character_revision import CharacterRevision
from app.models.scene import Scene
from app.repositories import CharacterRepository, CharacterRevisionRepository
from app.schemas.common import APIModel
from app.services.character_tracker import character_tracker

router = APIRouter(
    prefix="/projects/{project_id}/characters/{character_id}/revisions",
    tags=["character-revisions"],
)
project_router = APIRouter(
    prefix="/projects/{project_id}/character-revisions",
    tags=["character-revisions"],
)


class CharacterRevisionResponse(APIModel):
    id: str
    character_id: str
    field: str
    old_value: Any = None
    new_value: Any = None
    reason: str
    source: str
    scene_id: str | None
    status: str
    created_by: str
    applied_by: str | None
    created_at: str | None = None
    applied_at: str | None = None


class CharacterTimelineEntry(APIModel):
    """时间线一个节点：可能对应一个章节、也可能是"未关联章节"。"""
    chapter_id: str | None
    chapter_index: int | None
    chapter_title: str | None
    revisions: list[CharacterRevisionResponse]


class CharacterRevisionPendingCount(APIModel):
    character_id: str
    pending_count: int = Field(ge=0)


async def _ensure_character(db, *, project_id: str, character_id: str, organization_id: str):
    character = await CharacterRepository(db).get(
        character_id, organization_id=organization_id
    )
    if not character or character.project_id != project_id:
        raise NotFoundError("character_not_found")
    return character


@router.get("", response_model=list[CharacterRevisionResponse])
async def list_revisions(
    project_id: str,
    character_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    status: str | None = None,
    limit: int = 50,
):
    require_permission(user, "character:read", tenant)
    await _ensure_character(
        db,
        project_id=project_id,
        character_id=character_id,
        organization_id=tenant.organization_id,
    )
    stmt = (
        select(CharacterRevision)
        .where(
            CharacterRevision.organization_id == tenant.organization_id,
            CharacterRevision.character_id == character_id,
        )
        .order_by(CharacterRevision.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    if status:
        stmt = stmt.where(CharacterRevision.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows]


@router.post("/{revision_id}/apply", response_model=CharacterRevisionResponse)
async def apply_revision(
    project_id: str,
    character_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "character:write", tenant)
    await _ensure_character(
        db,
        project_id=project_id,
        character_id=character_id,
        organization_id=tenant.organization_id,
    )
    revision = await character_tracker.apply_revision(
        db,
        revision_id=revision_id,
        organization_id=tenant.organization_id,
        applied_by=user.id,
    )
    if revision.character_id != character_id:
        raise NotFoundError("character_revision_not_found")
    await db.commit()
    return _to_response(revision)


@router.post("/{revision_id}/reject", response_model=CharacterRevisionResponse)
async def reject_revision(
    project_id: str,
    character_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "character:write", tenant)
    await _ensure_character(
        db,
        project_id=project_id,
        character_id=character_id,
        organization_id=tenant.organization_id,
    )
    revision = await character_tracker.reject_revision(
        db,
        revision_id=revision_id,
        organization_id=tenant.organization_id,
        actor_id=user.id,
    )
    if revision.character_id != character_id:
        raise NotFoundError("character_revision_not_found")
    await db.commit()
    return _to_response(revision)


@router.post("/{revision_id}/rollback", response_model=CharacterRevisionResponse)
async def rollback_revision(
    project_id: str,
    character_id: str,
    revision_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """把目标 revision 重新 apply。基于其 new_value 生成一条新的
    source='user_edit' 记录并 apply，保留可追溯回滚轨迹。"""
    require_permission(user, "character:write", tenant)
    await _ensure_character(
        db,
        project_id=project_id,
        character_id=character_id,
        organization_id=tenant.organization_id,
    )
    revision = await character_tracker.rollback_to(
        db,
        revision_id=revision_id,
        organization_id=tenant.organization_id,
        actor_id=user.id,
    )
    if revision.character_id != character_id:
        raise NotFoundError("character_revision_not_found")
    await db.commit()
    return _to_response(revision)


@project_router.get(
    "/pending-count", response_model=list[CharacterRevisionPendingCount]
)
async def list_pending_count(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """聚合本项目所有人物的 pending 计数，给 BiblePage 人物卡显示 badge 用。"""
    require_permission(user, "character:read", tenant)
    stmt = (
        select(CharacterRevision.character_id)
        .where(
            CharacterRevision.organization_id == tenant.organization_id,
            CharacterRevision.project_id == project_id,
            CharacterRevision.status == "pending",
        )
    )
    rows = list((await db.execute(stmt)).scalars().all())
    counts: dict[str, int] = {}
    for cid in rows:
        counts[cid] = counts.get(cid, 0) + 1
    return [
        CharacterRevisionPendingCount(character_id=cid, pending_count=cnt)
        for cid, cnt in counts.items()
    ]


@router.get("/timeline", response_model=list[CharacterTimelineEntry])
async def character_timeline(
    project_id: str,
    character_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    """按章节聚合该人物的 applied revisions，构造演进时间线。

    - 有 scene_id 的 revision → 通过 scene.chapter_id 关联章节
    - 无 scene_id 的（手动 / Copilot 提案）→ 放到 "未关联章节" 桶
    - 输出按 chapter_index 升序；同章节内按 applied_at 升序
    """
    require_permission(user, "character:read", tenant)
    await _ensure_character(
        db,
        project_id=project_id,
        character_id=character_id,
        organization_id=tenant.organization_id,
    )

    # 仅 applied 走时间线；rejected / superseded / pending 不进
    rev_stmt = (
        select(CharacterRevision)
        .where(
            CharacterRevision.organization_id == tenant.organization_id,
            CharacterRevision.character_id == character_id,
            CharacterRevision.status == "applied",
        )
        .order_by(CharacterRevision.applied_at.asc())
    )
    revisions = list((await db.execute(rev_stmt)).scalars().all())
    if not revisions:
        return []

    scene_ids = {r.scene_id for r in revisions if r.scene_id}
    chapter_id_by_scene: dict[str, str] = {}
    if scene_ids:
        scene_stmt = select(Scene.id, Scene.chapter_id).where(
            Scene.organization_id == tenant.organization_id,
            Scene.project_id == project_id,
            Scene.id.in_(scene_ids),
        )
        for sid, cid in (await db.execute(scene_stmt)).all():
            if cid:
                chapter_id_by_scene[sid] = cid

    chapter_ids = set(chapter_id_by_scene.values())
    chapter_meta: dict[str, tuple[int, str]] = {}
    if chapter_ids:
        chap_stmt = select(
            Chapter.id, Chapter.chapter_index, Chapter.title
        ).where(
            Chapter.organization_id == tenant.organization_id,
            Chapter.project_id == project_id,
            Chapter.id.in_(chapter_ids),
        )
        for cid, idx, title in (await db.execute(chap_stmt)).all():
            chapter_meta[cid] = (idx, title or "")

    buckets: dict[str | None, list[CharacterRevision]] = {}
    for rev in revisions:
        chapter_id = chapter_id_by_scene.get(rev.scene_id) if rev.scene_id else None
        buckets.setdefault(chapter_id, []).append(rev)

    entries: list[CharacterTimelineEntry] = []
    for chapter_id, revs in buckets.items():
        if chapter_id and chapter_id in chapter_meta:
            idx, title = chapter_meta[chapter_id]
            entries.append(
                CharacterTimelineEntry(
                    chapter_id=chapter_id,
                    chapter_index=idx,
                    chapter_title=title,
                    revisions=[_to_response(r) for r in revs],
                )
            )
        else:
            entries.append(
                CharacterTimelineEntry(
                    chapter_id=None,
                    chapter_index=None,
                    chapter_title=None,
                    revisions=[_to_response(r) for r in revs],
                )
            )

    # 排序：未关联章节放最后；其余按 chapter_index 升序
    entries.sort(
        key=lambda e: (1 if e.chapter_index is None else 0, e.chapter_index or 0)
    )
    return entries


def _to_response(revision: CharacterRevision) -> CharacterRevisionResponse:
    return CharacterRevisionResponse(
        id=revision.id,
        character_id=revision.character_id,
        field=revision.field,
        old_value=revision.old_value,
        new_value=revision.new_value,
        reason=revision.reason,
        source=revision.source,
        scene_id=revision.scene_id,
        status=revision.status,
        created_by=revision.created_by,
        applied_by=revision.applied_by,
        created_at=revision.created_at.isoformat() if revision.created_at else None,
        applied_at=revision.applied_at.isoformat() if revision.applied_at else None,
    )
