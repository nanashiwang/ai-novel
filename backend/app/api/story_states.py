"""关键状态 API（第一阶段底座）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import select, update

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.chapter import Chapter
from app.models.chapter_state_requirement import ChapterStateRequirement
from app.models.continuity_issue import ContinuityIssue
from app.models.story_state_item import StoryStateItem
from app.models.story_state_maintenance_action import StoryStateMaintenanceAction
from app.repositories import (
    ChapterRepository,
    ChapterStateRequirementRepository,
    ProjectRepository,
    StoryStateHistoryRepository,
    StoryStateRepository,
)
from app.schemas.story_state import (
    ChapterStateRequirementCreateRequest,
    ChapterStateRequirementListResponse,
    ChapterStateRequirementPatchRequest,
    ChapterStateRequirementResponse,
    StoryStateDuplicateListResponse,
    StoryStateHistoryListResponse,
    StoryStateItemResponse,
    StoryStateListResponse,
    StoryStateMaintenanceActionListResponse,
    StoryStateMaintenanceActionResponse,
    StoryStateMergeRequest,
    StoryStateMergeResponse,
    StoryStatePatchRequest,
)
from app.services.story_state.maintainer import story_state_maintainer_service

router = APIRouter(prefix="/projects/{project_id}/story-states", tags=["story-states"])
chapter_router = APIRouter(prefix="/projects/{project_id}/chapters", tags=["story-states"])


async def _get_project_or_404(project_id: str, tenant: TenantDep, db: DbDep):
    project = await ProjectRepository(db).get(
        project_id,
        organization_id=tenant.organization_id,
    )
    if not project:
        raise NotFoundError("project_not_found")
    return project


async def _get_story_state_or_404(
    project_id: str,
    state_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> StoryStateItem:
    state = await StoryStateRepository(db).get(
        state_id,
        organization_id=tenant.organization_id,
    )
    if not state or state.project_id != project_id:
        raise NotFoundError("story_state_not_found")
    return state


async def _get_chapter_or_404(
    project_id: str,
    chapter_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> Chapter:
    chapter = await ChapterRepository(db).get(
        chapter_id,
        organization_id=tenant.organization_id,
    )
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found")
    return chapter


async def _get_requirement_or_404(
    project_id: str,
    chapter_id: str,
    requirement_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> ChapterStateRequirement:
    requirement = await ChapterStateRequirementRepository(db).get(
        requirement_id,
        organization_id=tenant.organization_id,
    )
    if (
        not requirement
        or requirement.project_id != project_id
        or requirement.chapter_id != chapter_id
    ):
        raise NotFoundError("chapter_state_requirement_not_found")
    return requirement


async def _get_source_issue_or_404(
    project_id: str,
    issue_id: str,
    tenant: TenantDep,
    db: DbDep,
) -> ContinuityIssue:
    result = await db.execute(
        select(ContinuityIssue).where(
            ContinuityIssue.organization_id == tenant.organization_id,
            ContinuityIssue.project_id == project_id,
            ContinuityIssue.id == issue_id,
        )
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise NotFoundError("continuity_issue_not_found")
    return issue


async def _build_requirement_responses(
    *,
    project_id: str,
    tenant: TenantDep,
    db: DbDep,
    items: list[ChapterStateRequirement],
) -> list[dict[str, Any]]:
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
                StoryStateItem.organization_id == tenant.organization_id,
                StoryStateItem.project_id == project_id,
                StoryStateItem.id.in_(state_ids),
            )
        )
        state_by_id = {state.id: state for state in result.scalars().all()}
    source_chapter_by_id: dict[str, Chapter] = {}
    if source_chapter_ids:
        result = await db.execute(
            select(Chapter).where(
                Chapter.organization_id == tenant.organization_id,
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
            "status": item.status or "active",
            "superseded_by_requirement_id": item.superseded_by_requirement_id,
            "source_issue_id": item.source_issue_id,
            "status_reason": item.status_reason or "",
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


async def _build_requirement_response(
    *,
    project_id: str,
    tenant: TenantDep,
    db: DbDep,
    item: ChapterStateRequirement,
) -> dict[str, Any]:
    responses = await _build_requirement_responses(
        project_id=project_id,
        tenant=tenant,
        db=db,
        items=[item],
    )
    return responses[0]


def _state_snapshot(state: StoryStateItem) -> dict[str, Any]:
    return {
        "entity_type": state.entity_type,
        "entity_id": state.entity_id,
        "state_type": state.state_type,
        "name": state.name,
        "status": state.status,
        "superseded_by_state_id": state.superseded_by_state_id,
        "status_reason": state.status_reason or "",
        "summary": state.summary,
        "value_json": dict(state.value_json or {}),
        "source_chapter_id": state.source_chapter_id,
        "source_scene_id": state.source_scene_id,
        "source_excerpt": state.source_excerpt,
        "updated_in_chapter_id": state.updated_in_chapter_id,
        "priority": state.priority,
        "is_hard_constraint": state.is_hard_constraint,
    }


def _state_response_payload(state: StoryStateItem) -> dict[str, Any]:
    return {
        "id": state.id,
        "entity_type": state.entity_type,
        "entity_id": state.entity_id,
        "state_type": state.state_type,
        "name": state.name,
        "status": state.status,
        "superseded_by_state_id": state.superseded_by_state_id,
        "status_reason": state.status_reason or "",
        "summary": state.summary,
        "value_json": dict(state.value_json or {}),
        "source_chapter_id": state.source_chapter_id,
        "source_scene_id": state.source_scene_id,
        "source_excerpt": state.source_excerpt,
        "updated_in_chapter_id": state.updated_in_chapter_id,
        "priority": state.priority,
        "is_hard_constraint": state.is_hard_constraint,
    }


def _compact_state_text(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _char_overlap_score(left: str, right: str) -> int:
    left_set = set(_compact_state_text(left))
    right_set = set(_compact_state_text(right))
    if not left_set or not right_set:
        return 0
    return int(100 * len(left_set & right_set) / len(left_set | right_set))


def _duplicate_score(left: StoryStateItem, right: StoryStateItem) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if left.entity_type == right.entity_type:
        score += 15
        reasons.append("实体类型一致")
    if left.state_type == right.state_type:
        score += 25
        reasons.append("状态类型一致")
    if left.entity_id and right.entity_id and left.entity_id == right.entity_id:
        score += 15
        reasons.append("实体 ID 一致")

    left_name = _compact_state_text(left.name or "")
    right_name = _compact_state_text(right.name or "")
    if left_name and right_name:
        if left_name == right_name:
            score += 35
            reasons.append("名称完全一致")
        elif left_name in right_name or right_name in left_name:
            score += 28
            reasons.append("名称互相包含")
        else:
            name_overlap = _char_overlap_score(left.name or "", right.name or "")
            if name_overlap >= 55:
                score += min(24, int(name_overlap * 0.35))
                reasons.append("名称高度相似")

    summary_overlap = _char_overlap_score(left.summary or "", right.summary or "")
    if summary_overlap >= 35:
        score += min(20, int(summary_overlap * 0.25))
        reasons.append("说明内容相似")

    return min(score, 100), reasons


def _merge_value_json(target: dict[str, Any], sources: list[StoryStateItem]) -> dict[str, Any]:
    merged = dict(target or {})
    for source in sources:
        source_value = dict(source.value_json or {})
        for key, value in source_value.items():
            merged.setdefault(key, value)
    return merged


@router.get("", response_model=StoryStateListResponse)
async def list_story_states(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    state_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    hard_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    items = await StoryStateRepository(db).list_filtered(
        organization_id=tenant.organization_id,
        project_id=project_id,
        state_type=state_type,
        status=status,
        entity_type=entity_type,
        hard_only=hard_only,
        limit=limit,
    )
    return StoryStateListResponse(items=list(items))


@router.get("/duplicate-candidates", response_model=StoryStateDuplicateListResponse)
async def list_story_state_duplicate_candidates(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=20, ge=1, le=100),
    threshold: int = Query(default=70, ge=40, le=100),
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    rows = list(
        await StoryStateRepository(db).list_filtered(
            organization_id=tenant.organization_id,
            project_id=project_id,
            limit=200,
        )
    )
    rows = [row for row in rows if (row.status or "active") != "inactive"]
    groups: list[dict[str, Any]] = []
    grouped_ids: set[str] = set()
    for index, anchor in enumerate(rows):
        if anchor.id in grouped_ids:
            continue
        candidates = []
        for candidate in rows[index + 1 :]:
            if candidate.id in grouped_ids:
                continue
            score, reasons = _duplicate_score(anchor, candidate)
            if score >= threshold:
                candidates.append(
                    {
                        "state": candidate,
                        "score": score,
                        "reasons": reasons,
                    }
                )
        if candidates:
            candidates.sort(key=lambda item: int(item["score"]), reverse=True)
            groups.append({"anchor": anchor, "candidates": candidates})
            grouped_ids.add(anchor.id)
            grouped_ids.update(item["state"].id for item in candidates)
        if len(groups) >= limit:
            break
    return StoryStateDuplicateListResponse(groups=groups)


@router.get(
    "/maintenance-actions",
    response_model=StoryStateMaintenanceActionListResponse,
)
async def list_story_state_maintenance_actions(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
    chapter_id: str | None = Query(default=None),
    scene_id: str | None = Query(default=None),
    draft_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    stmt = select(StoryStateMaintenanceAction).where(
        StoryStateMaintenanceAction.organization_id == tenant.organization_id,
        StoryStateMaintenanceAction.project_id == project_id,
    )
    if chapter_id:
        stmt = stmt.where(StoryStateMaintenanceAction.chapter_id == chapter_id)
    if scene_id:
        stmt = stmt.where(StoryStateMaintenanceAction.scene_id == scene_id)
    if draft_id:
        stmt = stmt.where(StoryStateMaintenanceAction.draft_id == draft_id)
    if status:
        stmt = stmt.where(StoryStateMaintenanceAction.status == status)
    if action_type:
        stmt = stmt.where(StoryStateMaintenanceAction.action_type == action_type)
    stmt = stmt.order_by(StoryStateMaintenanceAction.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return StoryStateMaintenanceActionListResponse(items=list(result.scalars().all()))


@router.post(
    "/maintenance-actions/{action_id}/rollback",
    response_model=StoryStateMaintenanceActionResponse,
)
async def rollback_story_state_maintenance_action(
    project_id: str,
    action_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    action = await story_state_maintainer_service.rollback_action(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
        action_id=action_id,
        created_by=user.id,
    )
    await db.commit()
    return action


@router.get("/{state_id}", response_model=StoryStateItemResponse)
async def get_story_state(
    project_id: str,
    state_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    return await _get_story_state_or_404(project_id, state_id, tenant, db)


@router.get("/{state_id}/history", response_model=StoryStateHistoryListResponse)
async def get_story_state_history(
    project_id: str,
    state_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_story_state_or_404(project_id, state_id, tenant, db)
    items = await StoryStateHistoryRepository(db).list_for_state(
        organization_id=tenant.organization_id,
        project_id=project_id,
        state_item_id=state_id,
    )
    return StoryStateHistoryListResponse(items=list(items))


@router.post("/{state_id}/merge", response_model=StoryStateMergeResponse)
async def merge_story_states(
    project_id: str,
    state_id: str,
    payload: StoryStateMergeRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    target = await _get_story_state_or_404(project_id, state_id, tenant, db)
    source_ids = list(dict.fromkeys(payload.source_state_ids))
    if target.id in source_ids:
        raise ConflictError("cannot_merge_state_into_self")

    source_rows = []
    for source_id in source_ids:
        source_rows.append(await _get_story_state_or_404(project_id, source_id, tenant, db))
    if not source_rows:
        raise ConflictError("merge_source_required")

    reason = (payload.reason or "").strip() or "manual_merge_story_state"
    history_repo = StoryStateHistoryRepository(db)
    before_target = _state_snapshot(target)
    source_snapshots = {source.id: _state_snapshot(source) for source in source_rows}

    if payload.summary is not None:
        clean_summary = payload.summary.strip()
        if clean_summary:
            target.summary = clean_summary
    elif not (target.summary or "").strip():
        target.summary = next((source.summary for source in source_rows if source.summary), "")

    if payload.value_json is not None:
        target.value_json = dict(payload.value_json or {})
    else:
        target.value_json = _merge_value_json(dict(target.value_json or {}), source_rows)

    if payload.priority is not None:
        target.priority = max(0, int(payload.priority or 0))
    else:
        target.priority = max(
            [int(target.priority or 0)]
            + [int(row.priority or 0) for row in source_rows]
        )

    if payload.is_hard_constraint is not None:
        target.is_hard_constraint = bool(payload.is_hard_constraint)
    else:
        target.is_hard_constraint = bool(target.is_hard_constraint) or any(
            bool(row.is_hard_constraint) for row in source_rows
        )
    target.status = "active"
    target.superseded_by_state_id = None
    target.status_reason = ""

    for source in source_rows:
        source.status = "inactive"
        source.superseded_by_state_id = target.id
        source.status_reason = reason

    requirement_result = await db.execute(
        update(ChapterStateRequirement)
        .where(
            ChapterStateRequirement.organization_id == tenant.organization_id,
            ChapterStateRequirement.project_id == project_id,
            ChapterStateRequirement.state_item_id.in_(source_ids),
        )
        .values(state_item_id=target.id)
    )
    issue_result = await db.execute(
        update(ContinuityIssue)
        .where(
            ContinuityIssue.organization_id == tenant.organization_id,
            ContinuityIssue.project_id == project_id,
            ContinuityIssue.story_state_item_id.in_(source_ids),
        )
        .values(story_state_item_id=target.id)
    )
    await db.flush()
    await history_repo.create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        state_item_id=target.id,
        chapter_id=target.updated_in_chapter_id,
        scene_id=target.source_scene_id,
        change_type="update",
        before_json=before_target,
        after_json=_state_snapshot(target),
        reason=reason,
        source_excerpt=target.source_excerpt,
        created_by=user.id,
    )
    for source in source_rows:
        await history_repo.create(
            organization_id=tenant.organization_id,
            project_id=project_id,
            state_item_id=source.id,
            chapter_id=source.updated_in_chapter_id,
            scene_id=source.source_scene_id,
            change_type="resolve",
            before_json=source_snapshots[source.id],
            after_json=_state_snapshot(source),
            reason=reason,
            source_excerpt=source.source_excerpt,
            created_by=user.id,
        )
    target_payload = _state_response_payload(target)
    await db.commit()
    return StoryStateMergeResponse(
        target=target_payload,
        merged_ids=source_ids,
        updated_requirement_count=int(requirement_result.rowcount or 0),
        updated_issue_count=int(issue_result.rowcount or 0),
    )


@router.patch("/{state_id}", response_model=StoryStateItemResponse)
async def patch_story_state(
    project_id: str,
    state_id: str,
    payload: StoryStatePatchRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    state = await _get_story_state_or_404(project_id, state_id, tenant, db)
    before = _state_snapshot(state)
    updates = payload.model_dump(exclude_none=True, exclude={"reason"})
    if "summary" in updates:
        updates["summary"] = str(updates["summary"]).strip()
    if "status_reason" in updates:
        updates["status_reason"] = str(updates["status_reason"]).strip()
    if "superseded_by_state_id" in updates:
        superseded_by = str(updates["superseded_by_state_id"] or "").strip()
        if not superseded_by:
            updates["superseded_by_state_id"] = None
        else:
            if superseded_by == state_id:
                raise ConflictError("cannot_supersede_state_by_self")
            await _get_story_state_or_404(project_id, superseded_by, tenant, db)
            updates["superseded_by_state_id"] = superseded_by
    updated = await StoryStateRepository(db).update(
        state_id,
        updates,
        organization_id=tenant.organization_id,
    )
    if not updated:
        raise NotFoundError("story_state_not_found")
    await StoryStateHistoryRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        state_item_id=state_id,
        chapter_id=updated.updated_in_chapter_id,
        scene_id=updated.source_scene_id,
        change_type="update",
        before_json=before,
        after_json=_state_snapshot(updated),
        reason=payload.reason or "manual_update_story_state",
        source_excerpt=updated.source_excerpt,
        created_by=user.id,
    )
    await db.commit()
    return updated


@chapter_router.get(
    "/{chapter_id}/state-requirements",
    response_model=ChapterStateRequirementListResponse,
)
async def list_chapter_state_requirements(
    project_id: str,
    chapter_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    items = await ChapterStateRequirementRepository(db).list_for_chapter(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    return ChapterStateRequirementListResponse(
        items=await _build_requirement_responses(
            project_id=project_id,
            tenant=tenant,
            db=db,
            items=list(items),
        ),
    )


@chapter_router.post(
    "/{chapter_id}/state-requirements",
    response_model=ChapterStateRequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chapter_state_requirement(
    project_id: str,
    chapter_id: str,
    payload: ChapterStateRequirementCreateRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    state = await _get_story_state_or_404(project_id, payload.state_item_id, tenant, db)
    source_issue_id = (payload.source_issue_id or "").strip() or None
    if source_issue_id:
        await _get_source_issue_or_404(project_id, source_issue_id, tenant, db)
    requirement = await ChapterStateRequirementRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
        state_item_id=state.id,
        requirement_type=payload.requirement_type,
        summary=payload.summary.strip() or state.summary,
        priority=max(0, int(payload.priority or 0)),
        origin_type="manual",
        status="active",
        source_issue_id=source_issue_id,
        source_chapter_id=None,
        source_scene_id=None,
        target_chapter_id=chapter_id,
    )
    await db.commit()
    return await _build_requirement_response(
        project_id=project_id,
        tenant=tenant,
        db=db,
        item=requirement,
    )


@chapter_router.patch(
    "/{chapter_id}/state-requirements/{requirement_id}",
    response_model=ChapterStateRequirementResponse,
)
async def patch_chapter_state_requirement(
    project_id: str,
    chapter_id: str,
    requirement_id: str,
    payload: ChapterStateRequirementPatchRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    requirement = await _get_requirement_or_404(
        project_id,
        chapter_id,
        requirement_id,
        tenant,
        db,
    )
    updates = payload.model_dump(exclude_none=True)
    if "summary" in updates:
        updates["summary"] = str(updates["summary"]).strip()
    if "status_reason" in updates:
        updates["status_reason"] = str(updates["status_reason"]).strip()
    if "superseded_by_requirement_id" in updates and not updates["superseded_by_requirement_id"]:
        updates["superseded_by_requirement_id"] = None
    if "priority" in updates:
        updates["priority"] = max(0, int(updates["priority"] or 0))
    updates["origin_type"] = "manual"
    updated = await ChapterStateRequirementRepository(db).update(
        requirement.id,
        updates,
        organization_id=tenant.organization_id,
    )
    if not updated:
        raise NotFoundError("chapter_state_requirement_not_found")
    await db.commit()
    return await _build_requirement_response(
        project_id=project_id,
        tenant=tenant,
        db=db,
        item=updated,
    )


@chapter_router.delete(
    "/{chapter_id}/state-requirements/{requirement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chapter_state_requirement(
    project_id: str,
    chapter_id: str,
    requirement_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    await _get_project_or_404(project_id, tenant, db)
    await _get_chapter_or_404(project_id, chapter_id, tenant, db)
    requirement = await _get_requirement_or_404(
        project_id,
        chapter_id,
        requirement_id,
        tenant,
        db,
    )
    await ChapterStateRequirementRepository(db).delete(
        requirement.id,
        organization_id=tenant.organization_id,
    )
    await db.commit()
