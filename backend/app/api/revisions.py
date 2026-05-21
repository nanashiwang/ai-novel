"""AI 设定共创 / Revision API。

核心原则：模型只生成结构化修改提案；用户显式应用后才写入故事圣经、
人物、世界观或剧情线，避免对话直接覆盖生产数据。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import asc

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models import Project, RevisionMessage, RevisionProposal
from app.repositories import (
    CharacterRepository,
    NovelSpecRepository,
    PlotThreadRepository,
    ProjectRepository,
    RevisionAppliedChangeRepository,
    RevisionMessageRepository,
    RevisionProposalRepository,
    RevisionSessionRepository,
    WorldItemRepository,
)
from app.schemas.common import APIModel
from app.services.model_gateway.service import model_gateway

router = APIRouter(prefix="/projects/{project_id}/revisions", tags=["revisions"])

RevisionTargetType = Literal[
    "project_settings",
    "story_bible",
    "character",
    "world_item",
    "plot_thread",
]
RevisionAction = Literal["update", "create"]

PROJECT_FIELDS = {
    "title",
    "genre",
    "target_word_count",
    "target_chapter_count",
    "style",
    "target_reader",
}
SPEC_FIELDS = {
    "premise",
    "theme",
    "genre",
    "tone",
    "target_reader",
    "narrative_pov",
    "style_guide",
    "constraints",
    "continuity_rules",
}
CHARACTER_FIELDS = {
    "name",
    "role",
    "description",
    "personality",
    "motivation",
    "secret",
    "arc",
    "relationships",
    "current_state",
}
WORLD_ITEM_FIELDS = {
    "type",
    "name",
    "description",
    "rules",
    "related_characters",
    "importance",
    "is_hard_rule",
}
PLOT_THREAD_FIELDS = {
    "title",
    "thread_type",
    "description",
    "status",
    "related_characters",
}


class RevisionProposalPayload(APIModel):
    target_type: RevisionTargetType
    target_id: str | None = None
    action: RevisionAction = "update"
    title: str = "设定优化提案"
    patch: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    impact: list[str] = Field(default_factory=list)


class RevisionChatRequest(APIModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    scope: str = Field(default="story_bible", max_length=64)
    target_type: RevisionTargetType | None = None
    target_id: str | None = None


class RevisionProposalResponse(RevisionProposalPayload):
    id: str
    session_id: str
    project_id: str
    status: str


class RevisionMessageResponse(APIModel):
    id: str
    session_id: str
    role: str
    content: str


class RevisionSessionResponse(APIModel):
    id: str
    project_id: str
    scope: str
    title: str
    status: str


class RevisionChatResponse(APIModel):
    session: RevisionSessionResponse
    reply: str
    messages: list[RevisionMessageResponse]
    proposals: list[RevisionProposalResponse]


class ApplyProposalResponse(APIModel):
    proposal: RevisionProposalResponse
    applied_change_id: str


async def _ensure_project(project_id: str, tenant: TenantDep, db: DbDep) -> Project:
    project = await ProjectRepository(db).get(project_id, organization_id=tenant.organization_id)
    if not project:
        raise NotFoundError("project_not_found", code="project_not_found")
    return project


def _public_row(row: Any, fields: set[str]) -> dict[str, Any]:
    return {field: getattr(row, field) for field in fields if hasattr(row, field)}


def _filter_patch(patch: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in (patch or {}).items() if key in allowed}


async def _load_context(db: DbDep, *, organization_id: str, project: Project) -> dict[str, Any]:
    spec = await NovelSpecRepository(db).get_by(
        organization_id=organization_id,
        project_id=project.id,
    )
    characters = await CharacterRepository(db).list(
        organization_id=organization_id,
        project_id=project.id,
    )
    world_items = await WorldItemRepository(db).list(
        organization_id=organization_id,
        project_id=project.id,
    )
    plot_threads = await PlotThreadRepository(db).list(
        organization_id=organization_id,
        project_id=project.id,
    )
    return {
        "project": _public_row(project, PROJECT_FIELDS | {"id", "status"}),
        "story_bible": None if not spec else _public_row(spec, SPEC_FIELDS | {"id"}),
        "characters": [
            _public_row(row, CHARACTER_FIELDS | {"id"}) for row in characters
        ],
        "world_items": [
            _public_row(row, WORLD_ITEM_FIELDS | {"id"}) for row in world_items
        ],
        "plot_threads": [
            _public_row(row, PLOT_THREAD_FIELDS | {"id"}) for row in plot_threads
        ],
    }


def _proposal_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "proposals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "target_type": {
                            "type": "string",
                            "enum": [
                                "project_settings",
                                "story_bible",
                                "character",
                                "world_item",
                                "plot_thread",
                            ],
                        },
                        "target_id": {"type": ["string", "null"]},
                        "action": {"type": "string", "enum": ["update", "create"]},
                        "title": {"type": "string"},
                        "patch": {"type": "object"},
                        "reason": {"type": "string"},
                        "impact": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["target_type", "action", "title", "patch", "reason"],
                },
            },
        },
        "required": ["reply", "proposals"],
    }


def _normalize_proposals(raw: dict[str, Any]) -> tuple[str, list[RevisionProposalPayload]]:
    reply = str(raw.get("reply") or "我整理了一组可应用的设定优化提案。").strip()
    proposals: list[RevisionProposalPayload] = []
    for item in raw.get("proposals") or []:
        if not isinstance(item, dict):
            continue
        try:
            proposal = RevisionProposalPayload.model_validate(
                {
                    "target_type": item.get("target_type"),
                    "target_id": item.get("target_id") or None,
                    "action": item.get("action") or "update",
                    "title": str(item.get("title") or "设定优化提案")[:200],
                    "patch": item.get("patch") if isinstance(item.get("patch"), dict) else {},
                    "reason": str(item.get("reason") or ""),
                    "impact": item.get("impact") if isinstance(item.get("impact"), list) else [],
                }
            )
        except Exception:  # noqa: BLE001
            continue
        if proposal.patch:
            proposals.append(proposal)
    return reply, proposals[:6]


async def _get_or_create_session(
    db: DbDep,
    *,
    project_id: str,
    organization_id: str,
    user_id: str,
    payload: RevisionChatRequest,
):
    repo = RevisionSessionRepository(db)
    if payload.session_id:
        session = await repo.get(payload.session_id, organization_id=organization_id)
        if not session or session.project_id != project_id:
            raise NotFoundError("revision_session_not_found", code="revision_session_not_found")
        return session
    title = payload.message.strip().replace("\n", " ")[:40] or "AI 设定共创"
    return await repo.create(
        organization_id=organization_id,
        project_id=project_id,
        created_by=user_id,
        scope=payload.scope,
        title=title,
        status="active",
    )


@router.get("/sessions/{session_id}", response_model=RevisionChatResponse)
async def get_revision_session(
    project_id: str,
    session_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    await _ensure_project(project_id, tenant, db)
    session = await RevisionSessionRepository(db).get(
        session_id, organization_id=tenant.organization_id
    )
    if not session or session.project_id != project_id:
        raise NotFoundError("revision_session_not_found", code="revision_session_not_found")
    messages = await RevisionMessageRepository(db).list(
        organization_id=tenant.organization_id,
        session_id=session.id,
        order_by=asc(RevisionMessage.created_at),
    )
    proposals = await RevisionProposalRepository(db).list(
        organization_id=tenant.organization_id,
        session_id=session.id,
        order_by=asc(RevisionProposal.created_at),
    )
    return RevisionChatResponse(
        session=session,
        reply="",
        messages=list(messages),
        proposals=list(proposals),
    )


@router.post("/chat", response_model=RevisionChatResponse)
async def chat_revision(
    project_id: str,
    payload: RevisionChatRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    project = await _ensure_project(project_id, tenant, db)
    session = await _get_or_create_session(
        db,
        project_id=project_id,
        organization_id=tenant.organization_id,
        user_id=user.id,
        payload=payload,
    )
    message_repo = RevisionMessageRepository(db)
    await message_repo.create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        session_id=session.id,
        role="user",
        content=payload.message,
        created_at=datetime.now(timezone.utc),
    )

    context = await _load_context(db, organization_id=tenant.organization_id, project=project)
    recent_messages = await message_repo.list(
        organization_id=tenant.organization_id,
        session_id=session.id,
        limit=8,
    )
    user_prompt = json.dumps(
        {
            "current_context": context,
            "conversation": [
                {"role": row.role, "content": row.content}
                for row in sorted(recent_messages, key=lambda item: item.created_at)
            ],
            "user_request": payload.message,
            "focus": {
                "scope": payload.scope,
                "target_type": payload.target_type,
                "target_id": payload.target_id,
            },
        },
        ensure_ascii=False,
    )
    raw = await model_gateway.generate_json(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
        job_id=None,
        task_type="revise_story_bible",
        system_prompt=(
            "你是专业长篇小说设定编辑。请基于当前故事圣经、角色、世界观和剧情线，"
            "与作者共创优化方案。必须只输出 JSON；不要直接改库。proposals 是可应用的"
            "结构化修改提案：target_id 必须优先使用上下文里的真实 id；create 可不填。"
        ),
        user_prompt=user_prompt,
        schema=_proposal_schema(),
        prompt_key="revision/story_bible_copilot",
        prompt_version="v1",
        temperature=0.5,
    )
    reply, proposals = _normalize_proposals(raw)
    await message_repo.create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        session_id=session.id,
        role="assistant",
        content=reply,
        created_at=datetime.now(timezone.utc),
    )
    proposal_repo = RevisionProposalRepository(db)
    created = []
    for proposal in proposals:
        created.append(
            await proposal_repo.create(
                organization_id=tenant.organization_id,
                project_id=project_id,
                session_id=session.id,
                status="pending",
                **proposal.model_dump(),
            )
        )
    await db.commit()
    messages = await message_repo.list(
        organization_id=tenant.organization_id,
        session_id=session.id,
        limit=20,
        order_by=asc(RevisionMessage.created_at),
    )
    return RevisionChatResponse(
        session=session,
        reply=reply,
        messages=list(messages),
        proposals=created,
    )


async def _apply_project_patch(project: Project, patch: dict[str, Any]) -> tuple[dict, dict, str]:
    values = _filter_patch(patch, PROJECT_FIELDS)
    before = _public_row(project, PROJECT_FIELDS | {"id"})
    for key, value in values.items():
        setattr(project, key, value)
    after = _public_row(project, PROJECT_FIELDS | {"id"})
    return before, after, project.id


async def _apply_spec_patch(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
    patch: dict[str, Any],
) -> tuple[dict, dict, str]:
    repo = NovelSpecRepository(db)
    spec = await repo.get_by(organization_id=organization_id, project_id=project_id)
    values = _filter_patch(patch, SPEC_FIELDS)
    if spec is None:
        spec = await repo.create(organization_id=organization_id, project_id=project_id, **values)
        return {}, _public_row(spec, SPEC_FIELDS | {"id"}), spec.id
    before = _public_row(spec, SPEC_FIELDS | {"id"})
    for key, value in values.items():
        setattr(spec, key, value)
    after = _public_row(spec, SPEC_FIELDS | {"id"})
    return before, after, spec.id


async def _apply_entity_patch(
    db: DbDep,
    *,
    repo: Any,
    model_name: str,
    organization_id: str,
    project_id: str,
    target_id: str | None,
    action: str,
    patch: dict[str, Any],
    fields: set[str],
    defaults: dict[str, Any],
) -> tuple[dict, dict, str]:
    values = {**defaults, **_filter_patch(patch, fields)}
    if action == "create":
        entity = await repo.create(
            organization_id=organization_id,
            project_id=project_id,
            **values,
        )
        return {}, _public_row(entity, fields | {"id"}), entity.id
    if not target_id:
        raise NotFoundError(f"{model_name}_not_found", code=f"{model_name}_not_found")
    entity = await repo.get(target_id, organization_id=organization_id)
    if not entity or entity.project_id != project_id:
        raise NotFoundError(f"{model_name}_not_found", code=f"{model_name}_not_found")
    before = _public_row(entity, fields | {"id"})
    for key, value in _filter_patch(patch, fields).items():
        setattr(entity, key, value)
    after = _public_row(entity, fields | {"id"})
    return before, after, entity.id


@router.post("/proposals/{proposal_id}/apply", response_model=ApplyProposalResponse)
async def apply_revision_proposal(
    project_id: str,
    proposal_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    project = await _ensure_project(project_id, tenant, db)
    proposal_repo = RevisionProposalRepository(db)
    proposal = await proposal_repo.get(proposal_id, organization_id=tenant.organization_id)
    if not proposal or proposal.project_id != project_id:
        raise NotFoundError("revision_proposal_not_found", code="revision_proposal_not_found")
    if proposal.status == "applied":
        raise ConflictError(
            "revision_proposal_already_applied",
            code="revision_proposal_already_applied",
        )
    if proposal.action not in {"update", "create"}:
        raise ConflictError("revision_action_not_supported", code="revision_action_not_supported")

    target_type = proposal.target_type
    if target_type == "project_settings":
        before, after, target_id = await _apply_project_patch(project, proposal.patch)
    elif target_type == "story_bible":
        before, after, target_id = await _apply_spec_patch(
            db,
            organization_id=tenant.organization_id,
            project_id=project_id,
            patch=proposal.patch,
        )
    elif target_type == "character":
        before, after, target_id = await _apply_entity_patch(
            db,
            repo=CharacterRepository(db),
            model_name="character",
            organization_id=tenant.organization_id,
            project_id=project_id,
            target_id=proposal.target_id,
            action=proposal.action,
            patch=proposal.patch,
            fields=CHARACTER_FIELDS,
            defaults={"name": "未命名角色"},
        )
    elif target_type == "world_item":
        before, after, target_id = await _apply_entity_patch(
            db,
            repo=WorldItemRepository(db),
            model_name="world_item",
            organization_id=tenant.organization_id,
            project_id=project_id,
            target_id=proposal.target_id,
            action=proposal.action,
            patch=proposal.patch,
            fields=WORLD_ITEM_FIELDS,
            defaults={"type": "rule", "name": "未命名设定"},
        )
    elif target_type == "plot_thread":
        before, after, target_id = await _apply_entity_patch(
            db,
            repo=PlotThreadRepository(db),
            model_name="plot_thread",
            organization_id=tenant.organization_id,
            project_id=project_id,
            target_id=proposal.target_id,
            action=proposal.action,
            patch=proposal.patch,
            fields=PLOT_THREAD_FIELDS,
            defaults={"title": "未命名剧情线"},
        )
    else:
        raise ConflictError("revision_target_not_supported", code="revision_target_not_supported")

    proposal.status = "applied"
    proposal.target_id = target_id
    await db.flush()
    change = await RevisionAppliedChangeRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        session_id=proposal.session_id,
        proposal_id=proposal.id,
        target_type=proposal.target_type,
        target_id=target_id,
        before_data=before,
        after_data=after,
        applied_by=user.id,
    )
    await db.commit()
    return ApplyProposalResponse(proposal=proposal, applied_change_id=change.id)
