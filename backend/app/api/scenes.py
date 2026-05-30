"""场景 API。"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.models.chapter import Chapter
from app.models.chapter_state_requirement import ChapterStateRequirement
from app.models.story_state_item import StoryStateItem
from app.repositories import ChapterRepository, SceneRepository
from app.schemas.common import APIModel
from app.schemas.story_state import AntiForgettingPreviewResponse
from app.services.story_state.prompting import build_anti_forgetting_preview

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["scenes"])


class ScenePayload(APIModel):
    chapter_id: str
    scene_index: int
    title: str
    time_marker: str = ""
    location: str = ""
    characters: list[str] = []
    scene_purpose: str = ""
    entry_state: str = ""
    exit_state: str = ""
    goal: str = ""
    conflict: str = ""
    must_include: list[str] = []
    must_avoid: list[str] = []
    emotion_start: str = ""
    emotion_end: str = ""
    reveal: str = ""
    hook: str = ""
    status: str = "planned"
    target_words: int = 0
    beat_start: int | None = None
    beat_end: int | None = None
    beat_group_summary: str = ""
    budget_reason: str = ""
    # Sprint 14-C6：单场景 POV 锚定；空 → 回落 spec.narrative_pov
    pov_character_name: str | None = None


class SceneResponse(ScenePayload):
    id: str
    organization_id: str
    project_id: str


async def _build_requirement_responses(
    *,
    project_id: str,
    organization_id: str,
    db: DbDep,
    items: list[ChapterStateRequirement],
) -> list[dict[str, object]]:
    state_ids = {item.state_item_id for item in items}
    source_chapter_ids = {
        item.source_chapter_id
        for item in items
        if item.source_chapter_id
    }
    state_by_id: dict[str, StoryStateItem] = {}
    if state_ids:
        result = await db.execute(
            select(StoryStateItem).where(
                StoryStateItem.organization_id == organization_id,
                StoryStateItem.project_id == project_id,
                StoryStateItem.id.in_(state_ids),
            )
        )
        state_by_id = {state.id: state for state in result.scalars().all()}
    source_chapter_by_id: dict[str, Chapter] = {}
    if source_chapter_ids:
        result = await db.execute(
            select(Chapter).where(
                Chapter.organization_id == organization_id,
                Chapter.project_id == project_id,
                Chapter.id.in_(source_chapter_ids),
            )
        )
        source_chapter_by_id = {row.id: row for row in result.scalars().all()}
    return [
        {
            "id": item.id,
            "state_item_id": item.state_item_id,
            "requirement_type": item.requirement_type,
            "summary": item.summary,
            "priority": item.priority,
            "origin_type": item.origin_type or "current_chapter_extract",
            "source_chapter_id": item.source_chapter_id,
            "source_chapter_index": (
                source_chapter_by_id[item.source_chapter_id].chapter_index
                if item.source_chapter_id in source_chapter_by_id
                else None
            ),
            "source_chapter_title": (
                source_chapter_by_id[item.source_chapter_id].title
                if item.source_chapter_id in source_chapter_by_id
                else None
            ),
            "source_scene_id": item.source_scene_id,
            "target_chapter_id": item.target_chapter_id or item.chapter_id,
            "state_item": state_by_id.get(item.state_item_id),
        }
        for item in items
    ]


@router.get("", response_model=list[SceneResponse])
async def list_scenes(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    chapter_id: str | None = None,
):
    require_permission(user, "scene:read", tenant)
    rows = await SceneRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    return rows


@router.post("", response_model=SceneResponse, status_code=201)
async def create_scene(
    project_id: str,
    payload: ScenePayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:write", tenant)
    chapter = await ChapterRepository(db).get(
        payload.chapter_id, organization_id=tenant.organization_id
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    scene = await SceneRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        **payload.model_dump(),
    )
    await db.commit()
    return scene


@router.get("/{scene_id}", response_model=SceneResponse)
async def get_scene(
    project_id: str,
    scene_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:read", tenant)
    scene = await SceneRepository(db).get(scene_id, organization_id=tenant.organization_id)
    if not scene or scene.project_id != project_id:
        raise NotFoundError("scene_not_found")
    return scene


@router.get("/{scene_id}/anti-forgetting-preview", response_model=AntiForgettingPreviewResponse)
async def preview_scene_anti_forgetting(
    project_id: str,
    scene_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:read", tenant)
    scene = await SceneRepository(db).get(scene_id, organization_id=tenant.organization_id)
    if not scene or scene.project_id != project_id:
        raise NotFoundError("scene_not_found")
    chapter = await ChapterRepository(db).get(
        scene.chapter_id,
        organization_id=tenant.organization_id,
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    preview = await build_anti_forgetting_preview(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter=chapter,
        scene=scene,
        purpose="writing",
    )
    return AntiForgettingPreviewResponse(
        project_id=project_id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        purpose="writing",
        prompt_block=preview.prompt_block,
        meta=preview.meta,
        requirements=await _build_requirement_responses(
            project_id=project_id,
            organization_id=tenant.organization_id,
            db=db,
            items=preview.requirements,
        ),
        story_states=preview.story_states,
    )


@router.patch("/{scene_id}", response_model=SceneResponse)
async def update_scene(
    project_id: str,
    scene_id: str,
    payload: ScenePayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:write", tenant)
    chapter = await ChapterRepository(db).get(
        payload.chapter_id, organization_id=tenant.organization_id
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    scene = await SceneRepository(db).update(
        scene_id, payload.model_dump(), organization_id=tenant.organization_id
    )
    if not scene or scene.project_id != project_id:
        raise NotFoundError("scene_not_found")
    await db.commit()
    return scene


@router.delete("/{scene_id}", status_code=204)
async def delete_scene(
    project_id: str,
    scene_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "scene:write", tenant)
    repo = SceneRepository(db)
    scene = await repo.get(scene_id, organization_id=tenant.organization_id)
    if not scene or scene.project_id != project_id:
        raise NotFoundError("scene_not_found")
    await repo.delete(scene_id, organization_id=tenant.organization_id)
    await db.commit()
