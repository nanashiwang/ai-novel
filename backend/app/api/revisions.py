"""AI 设定共创 / Revision API。

核心原则：模型只生成结构化修改提案；用户显式应用后才写入故事圣经、
人物、世界观或剧情线，避免对话直接覆盖生产数据。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import asc, func, select

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models import (
    Chapter,
    Character,
    CharacterRevision,
    ContinuityIssue,
    DraftVersion,
    GenerationJob,
    MemoryEntry,
    PlotThread,
    PlotThreadRevision,
    Project,
    RevisionAppliedChange,
    RevisionMessage,
    RevisionProposal,
    Scene,
    WorldItem,
    WorldItemRevision,
)
from app.repositories import (
    ChapterRepository,
    CharacterRepository,
    NovelSpecRepository,
    PlotThreadRepository,
    ProjectRepository,
    RevisionAppliedChangeRepository,
    RevisionMessageRepository,
    RevisionProposalRepository,
    RevisionSessionRepository,
    SceneRepository,
    WorldItemRepository,
)
from app.schemas.common import APIModel
from app.schemas.generation import GenerationJobResponse
from app.schemas.story_generation import StoryBibleContract
from app.services.character_tracker import character_tracker
from app.services.generation.service import generation_service
from app.services.model_gateway.service import model_gateway
from app.services.novel_planner.service import novel_planner_service

router = APIRouter(prefix="/projects/{project_id}/revisions", tags=["revisions"])
logger = logging.getLogger(__name__)
REVISION_MODEL_TIMEOUT_SECONDS = 120

RevisionTargetType = Literal[
    "project_settings",
    "story_bible",
    "character",
    "world_item",
    "plot_thread",
    "chapter",
    "story_bible_bundle",
]
RevisionAction = Literal["update", "create"]
RevisionMode = Literal["patch", "full_project_rewrite"]

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
CHAPTER_FIELDS = {
    "title",
    "summary",
    "goal",
    "conflict",
    "ending_hook",
    "status",
}


class RevisionProposalPayload(APIModel):
    target_type: RevisionTargetType
    target_id: str | None = None
    action: RevisionAction = "update"
    title: str = "设定优化提案"
    patch: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    impact: list[str] = Field(default_factory=list)
    group_id: str | None = None
    group_title: str = ""
    is_primary: bool = False
    risk_notes: list[str] = Field(default_factory=list)


class RevisionChatRequest(APIModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    scope: str = Field(default="story_bible", max_length=64)
    target_type: RevisionTargetType | None = None
    target_id: str | None = None
    mode: RevisionMode = "patch"


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
    job: GenerationJobResponse | None = None


class ApplyProposalResponse(APIModel):
    proposal: RevisionProposalResponse
    applied_change_id: str


class ApplyProposalGroupResponse(APIModel):
    proposals: list[RevisionProposalResponse]
    applied_change_ids: list[str]


class ApplyProposalWithRebuildRequest(APIModel):
    estimate_words: int = Field(default=20_000, ge=1_000, le=1_500_000)
    topic: str = ""
    target_chapters: int | None = Field(default=None, ge=1, le=2000)
    scenes_per_chapter: int = Field(default=3, ge=1, le=8)
    write_drafts: bool = True


class ApplyProposalWithRebuildResponse(APIModel):
    proposal: RevisionProposalResponse
    applied_change_id: str
    job: GenerationJobResponse


async def _ensure_project(project_id: str, tenant: TenantDep, db: DbDep) -> Project:
    project = await ProjectRepository(db).get(project_id, organization_id=tenant.organization_id)
    if not project:
        raise NotFoundError("project_not_found", code="project_not_found")
    return project


def _public_row(row: Any, fields: set[str]) -> dict[str, Any]:
    return {field: getattr(row, field) for field in fields if hasattr(row, field)}


_NULL_VALUE = object()


def _drop_nulls(value: Any) -> Any:
    if value is None:
        return _NULL_VALUE
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            cleaned = _drop_nulls(item)
            if cleaned is not _NULL_VALUE:
                cleaned_items.append(cleaned)
        return cleaned_items
    if isinstance(value, dict):
        cleaned_dict = {}
        for key, item in value.items():
            cleaned = _drop_nulls(item)
            if cleaned is not _NULL_VALUE:
                cleaned_dict[key] = cleaned
        return cleaned_dict
    return value


def _filter_patch(patch: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        return {}
    values: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in allowed:
            continue
        cleaned = _drop_nulls(value)
        if cleaned is _NULL_VALUE:
            continue
        values[key] = cleaned
    return values


def _require_effective_patch(values: dict[str, Any]) -> None:
    if not values:
        raise ConflictError(
            "提案没有可应用的有效修改，请重新生成 AI 优化。",
            code="revision_patch_empty",
        )


def _target_fields(target_type: Any) -> set[str] | None:
    return {
        "project_settings": PROJECT_FIELDS,
        "story_bible": SPEC_FIELDS,
        "character": CHARACTER_FIELDS,
        "world_item": WORLD_ITEM_FIELDS,
        "plot_thread": PLOT_THREAD_FIELDS,
        "chapter": CHAPTER_FIELDS,
    }.get(str(target_type or ""))


def _filter_patch_for_target(target_type: Any, patch: Any) -> dict[str, Any]:
    if str(target_type or "") == "story_bible_bundle":
        if isinstance(patch, dict) and isinstance(patch.get("story_bible"), dict):
            return patch
        return {}
    fields = _target_fields(target_type)
    if fields is None:
        return {}
    return _filter_patch(patch, fields)


def _json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False)


def _join_text(*parts: Any) -> str:
    return "\n".join(text for part in parts if (text := _json_text(part)))


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _json_text(item))]
    text = _json_text(value)
    return [text] if text else []


def _new_group_id() -> str:
    return f"revgrp_{uuid4().hex}"


def _is_primary_target(
    target_type: Any,
    *,
    focus_target_type: Any = None,
    focus_target_id: str | None = None,
) -> bool:
    if not focus_target_type:
        return False
    if str(target_type or "") != str(focus_target_type):
        return False
    if not focus_target_id:
        return True
    return True


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
    chapters = await ChapterRepository(db).list(
        organization_id=organization_id,
        project_id=project.id,
        limit=200,
        order_by=asc(ChapterRepository.model.chapter_index),
    )
    return {
        "project": _public_row(project, PROJECT_FIELDS | {"id", "status"}),
        "story_bible": None if not spec else _public_row(spec, SPEC_FIELDS | {"id"}),
        "characters": [_public_row(row, CHARACTER_FIELDS | {"id"}) for row in characters],
        "world_items": [_public_row(row, WORLD_ITEM_FIELDS | {"id"}) for row in world_items],
        "plot_threads": [_public_row(row, PLOT_THREAD_FIELDS | {"id"}) for row in plot_threads],
        "chapters": [
            _public_row(row, CHAPTER_FIELDS | {"id", "chapter_index"}) for row in chapters
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
                                "chapter",
                                "story_bible_bundle",
                            ],
                        },
                        "target_id": {"type": ["string", "null"]},
                        "action": {"type": "string", "enum": ["update", "create"]},
                        "title": {"type": "string"},
                        "patch": {"type": "object"},
                        "reason": {"type": "string"},
                        "impact": {"type": "array", "items": {"type": "string"}},
                        "group_id": {"type": ["string", "null"]},
                        "group_title": {"type": "string"},
                        "is_primary": {"type": "boolean"},
                        "risk_notes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["target_type", "action", "title", "patch", "reason"],
                },
            },
        },
        "required": ["reply", "proposals"],
    }


def _story_bible_bundle_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "summary": {"type": "string"},
            "risk_notes": {"type": "array", "items": {"type": "string"}},
            "story_bible": StoryBibleContract.model_json_schema(),
        },
        "required": ["reply", "story_bible"],
    }


def _find_character_id(context: dict[str, Any], name: str) -> str | None:
    if not name:
        return None
    for character in context.get("characters") or []:
        if not isinstance(character, dict):
            continue
        if str(character.get("name") or "").strip() == name:
            return str(character.get("id") or "") or None
    return None


def _find_chapter_id(context: dict[str, Any], chapter_index: Any) -> str | None:
    if chapter_index is None:
        return None
    try:
        index = int(chapter_index)
    except (TypeError, ValueError):
        return None
    for chapter in context.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        if int(chapter.get("chapter_index") or 0) == index:
            return str(chapter.get("id") or "") or None
    return None


_ADVICE_KEYS = {
    "type",
    "content",
    "description",
    "changes",
    "implementation",
    "problem",
    "core_adjustment",
    "application_notes",
    "long_form_value",
    "male_lead_profile",
    "character_profile",
    "rule_upgrades",
    "factions",
    "layers",
    "folded_world_layers",
    "expanded_world_model",
    "new_core_conflicts",
    "male_lead_team_growth",
}


def _looks_like_advice_item(item: dict[str, Any]) -> bool:
    return any(key in item for key in _ADVICE_KEYS)


def _fallback_proposals_from_advice(
    item: dict[str, Any],
    *,
    context: dict[str, Any],
    focus_target_type: Any = None,
    focus_target_id: str | None = None,
) -> list[RevisionProposalPayload]:
    title = str(item.get("title") or "设定优化提案")[:200]
    advice_type = str(item.get("type") or "").strip().lower()
    advice_text = _join_text(
        item.get("content"),
        item.get("description"),
        item.get("changes"),
        item.get("implementation"),
        item.get("layers"),
        item.get("core_adjustment"),
        item.get("application_notes"),
        item.get("long_form_value"),
    )
    reason = _join_text(item.get("problem"), item.get("core_adjustment"), item.get("content"))
    group_id = _new_group_id()
    group_title = str(item.get("group_title") or title or "联动设定优化")[:200]
    risk_notes = _text_list(
        item.get("risk_notes") or item.get("risk") or item.get("application_notes")
    )
    proposals: list[RevisionProposalPayload] = []

    story_patch = _filter_patch(
        {
            "premise": item.get("premise"),
            "theme": item.get("theme") or item.get("core_conflict_upgrade"),
            "genre": item.get("genre"),
            "tone": item.get("tone"),
            "target_reader": item.get("target_reader"),
            "narrative_pov": item.get("narrative_pov"),
            "style_guide": item.get("style_guide"),
            "constraints": item.get("constraints"),
            "continuity_rules": item.get("continuity_rules"),
        },
        SPEC_FIELDS,
    )
    if not story_patch:
        continuity_rule = _join_text(
            item.get("content"),
            item.get("description"),
            item.get("changes"),
            item.get("implementation"),
            item.get("core_adjustment"),
            item.get("application_notes"),
            item.get("long_form_value"),
        )
        if continuity_rule:
            story_patch = {"continuity_rules": [continuity_rule]}
            if (
                "position" in advice_type
                or "premise" in advice_type
                or "定位" in title
                or "核心" in title
            ):
                maybe_genre = (
                    title.replace("类型定位调整为", "").replace("定位为", "").strip(" ：:")
                )
                if maybe_genre and maybe_genre != title:
                    story_patch["genre"] = maybe_genre[:120]
    if story_patch:
        proposals.append(
            RevisionProposalPayload(
                target_type="story_bible",
                action="update",
                title=title,
                patch=story_patch,
                reason=reason or "将 AI 建议写入故事圣经规则，避免只停留在聊天文本。",
                impact=["story_bible"],
            )
        )

    profile = item.get("male_lead_profile") or item.get("character_profile")
    if profile is None and ("protagonist" in advice_type or "主角" in title or "男主" in title):
        first_character = next(
            (row for row in context.get("characters") or [] if isinstance(row, dict)),
            {},
        )
        if first_character:
            profile = {
                "name": first_character.get("name"),
                "role": first_character.get("role"),
                "motivation": advice_text,
                "arc": advice_text,
            }
    if isinstance(profile, dict):
        name = str(profile.get("name") or "").strip()
        character_patch = _filter_patch(
            {
                "name": name,
                "role": profile.get("role"),
                "description": _join_text(
                    profile.get("surface_identity"),
                    profile.get("male_frequency_hook"),
                    profile.get("true_identity"),
                    profile.get("description"),
                ),
                "personality": profile.get("personality"),
                "motivation": profile.get("core_motivation") or profile.get("motivation"),
                "secret": profile.get("secret"),
                "arc": profile.get("ability_arc") or profile.get("arc"),
                "current_state": {
                    key: value
                    for key, value in {
                        "inner_wound": profile.get("inner_wound"),
                        "true_identity": profile.get("true_identity"),
                    }.items()
                    if value
                },
            },
            CHARACTER_FIELDS,
        )
        if character_patch:
            target_id = _find_character_id(context, name)
            proposals.append(
                RevisionProposalPayload(
                    target_type="character",
                    target_id=target_id,
                    action="update" if target_id else "create",
                    title=f"{title}：人物落库",
                    patch=character_patch,
                    reason=reason or "把 AI 建议中的人物设定转为可应用人物补丁。",
                    impact=["characters"],
                )
            )

    world_description = _join_text(
        item.get("content") if "world" in advice_type or "世界" in title else None,
        item.get("implementation") if "world" in advice_type or "世界" in title else None,
        item.get("layers"),
        item.get("core_adjustment"),
        item.get("expanded_world_model"),
        item.get("folded_world_layers"),
    )
    rules = item.get("rule_upgrades") or item.get("layers")
    if world_description or rules:
        proposals.append(
            RevisionProposalPayload(
                target_type="world_item",
                action="create",
                title=f"{title}：世界观落库",
                patch={
                    "type": "rule",
                    "name": title[:80],
                    "description": world_description or title,
                    "rules": {"items": rules} if isinstance(rules, list) else {},
                    "importance": "high",
                    "is_hard_rule": True,
                },
                reason=reason or "把 AI 建议中的世界规则转为可应用世界观条目。",
                impact=["world_items"],
            )
        )

    factions = item.get("factions")
    if isinstance(factions, list):
        for faction in factions[:3]:
            if not isinstance(faction, dict):
                continue
            name = str(faction.get("name") or "未命名势力").strip()
            proposals.append(
                RevisionProposalPayload(
                    target_type="world_item",
                    action="create",
                    title=f"新增势力：{name}"[:200],
                    patch={
                        "type": "faction",
                        "name": name,
                        "description": _join_text(
                            faction.get("surface_identity"),
                            faction.get("goal"),
                            faction.get("method"),
                            faction.get("conflict_with_male_lead"),
                        ),
                        "rules": {
                            "leader": faction.get("leader"),
                            "resources": faction.get("resources"),
                            "internal_crack": faction.get("internal_crack"),
                        },
                        "importance": "high",
                        "is_hard_rule": False,
                    },
                    reason=reason or "把 AI 建议中的势力格局转为可应用世界观条目。",
                    impact=["world_items", "plot_threads"],
                )
            )

    thread_description = _join_text(
        item.get("content"),
        item.get("implementation"),
        item.get("changes"),
        item.get("core_adjustment"),
        item.get("new_core_conflicts"),
        item.get("male_lead_team_growth"),
        item.get("long_form_value"),
    )
    if thread_description:
        proposals.append(
            RevisionProposalPayload(
                target_type="plot_thread",
                action="create",
                title=title[:200],
                patch={
                    "title": title[:200],
                    "thread_type": "main",
                    "description": thread_description,
                    "status": "open",
                },
                reason=reason or "把 AI 建议中的长期冲突引擎转为可应用剧情线。",
                impact=["plot_threads"],
            )
        )

    chapter_source = (
        item.get("chapter_patch") if isinstance(item.get("chapter_patch"), dict) else item
    )
    chapter_patch = _filter_patch(
        {
            "title": chapter_source.get("chapter_title") or chapter_source.get("title"),
            "summary": chapter_source.get("summary"),
            "goal": chapter_source.get("goal"),
            "conflict": chapter_source.get("conflict"),
            "ending_hook": chapter_source.get("ending_hook") or chapter_source.get("hook"),
            "status": chapter_source.get("status"),
        },
        CHAPTER_FIELDS,
    )
    chapter_target_id = (
        str(item.get("target_id") or item.get("chapter_id") or "").strip()
        or _find_chapter_id(context, item.get("chapter_index"))
        or None
    )
    if chapter_patch and chapter_target_id:
        proposals.append(
            RevisionProposalPayload(
                target_type="chapter",
                target_id=chapter_target_id,
                action="update",
                title=f"{title}：章节大纲优化"[:200],
                patch=chapter_patch,
                reason=reason or "把 AI 建议中的章节节奏、冲突或钩子转为可应用大纲补丁。",
                impact=["chapters"],
            )
        )

    primary_assigned = False
    for index, proposal in enumerate(proposals):
        proposal.group_id = group_id if len(proposals) > 1 else None
        proposal.group_title = group_title if len(proposals) > 1 else ""
        proposal.risk_notes = risk_notes
        is_primary = _is_primary_target(
            proposal.target_type,
            focus_target_type=focus_target_type,
            focus_target_id=focus_target_id,
        )
        if is_primary or (not primary_assigned and index == 0):
            proposal.is_primary = True
            primary_assigned = True
    return proposals


def _normalize_proposals(
    raw: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    focus_target_type: Any = None,
    focus_target_id: str | None = None,
) -> tuple[str, list[RevisionProposalPayload]]:
    reply = str(raw.get("reply") or "我整理了一组可应用的设定优化提案。").strip()
    proposals: list[RevisionProposalPayload] = []
    raw_items = raw.get("proposals")
    if not raw_items and isinstance(raw.get("suggestions"), list):
        raw_items = raw.get("suggestions")
    if not raw_items and isinstance(raw.get("changes"), list):
        raw_items = raw.get("changes")
    if not raw_items and _looks_like_advice_item(raw):
        raw_items = [raw]
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        target_type = item.get("target_type")
        patch = _filter_patch_for_target(target_type, item.get("patch"))
        if not target_type or not patch:
            if _looks_like_advice_item(item):
                proposals.extend(
                    _fallback_proposals_from_advice(
                        item,
                        context=context or {},
                        focus_target_type=focus_target_type,
                        focus_target_id=focus_target_id,
                    )
                )
            continue
        group_id = (str(item.get("group_id") or "").strip()[:64]) or None
        try:
            proposal = RevisionProposalPayload.model_validate(
                {
                    "target_type": target_type,
                    "target_id": item.get("target_id") or None,
                    "action": item.get("action") or "update",
                    "title": str(item.get("title") or "设定优化提案")[:200],
                    "patch": patch,
                    "reason": str(item.get("reason") or ""),
                    "impact": item.get("impact") if isinstance(item.get("impact"), list) else [],
                    "group_id": group_id,
                    "group_title": str(item.get("group_title") or "")[:200],
                    "is_primary": bool(item.get("is_primary"))
                    or _is_primary_target(
                        target_type,
                        focus_target_type=focus_target_type,
                        focus_target_id=focus_target_id,
                    ),
                    "risk_notes": _text_list(item.get("risk_notes")),
                }
            )
        except Exception:  # noqa: BLE001
            continue
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


def _story_bible_counts(bible: StoryBibleContract) -> dict[str, int]:
    return {
        "characters": len(bible.main_characters or []),
        "locations": len(bible.locations or []),
        "factions": len(bible.factions or []),
        "world_rules": len(bible.world_rules or []),
        "plot_threads": len(bible.plot_threads or []),
    }


def _context_counts(context: dict[str, Any]) -> dict[str, int]:
    return {
        "characters": len(context.get("characters") or []),
        "world_items": len(context.get("world_items") or []),
        "plot_threads": len(context.get("plot_threads") or []),
        "chapters": len(context.get("chapters") or []),
    }


async def _generate_story_bible_bundle_proposals(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
    project: Project,
    payload: RevisionChatRequest,
    context: dict[str, Any],
) -> tuple[str, list[RevisionProposalPayload]]:
    compact_context = {
        "project": context.get("project"),
        "story_bible": context.get("story_bible"),
        "characters": (context.get("characters") or [])[:12],
        "world_items": (context.get("world_items") or [])[:20],
        "plot_threads": (context.get("plot_threads") or [])[:20],
        "chapter_count": len(context.get("chapters") or []),
        "chapter_samples": (context.get("chapters") or [])[:8],
    }
    user_prompt = json.dumps(
        {
            "current_context": compact_context,
            "user_request": payload.message,
            "focus": {
                "scope": payload.scope,
                "target_type": payload.target_type,
                "target_id": payload.target_id,
            },
            "output_contract": "StoryBibleContract",
        },
        ensure_ascii=False,
    )
    raw = await model_gateway.generate_json(
        db,
        organization_id=organization_id,
        project_id=project_id,
        job_id=None,
        task_type="revise_story_bible_bundle",
        system_prompt=(
            "你是商业长篇小说总编辑。用户要求的是全项目级重构：必须基于当前项目"
            "全局上下文和用户修改要求，输出一份完整新版故事圣经快照 story_bible，"
            "字段必须符合 StoryBibleContract。不要输出泛泛建议，不要只列方向；"
            "要把 Premise、Theme、Genre、Tone、POV、Style、人物、世界观、剧情线"
            "全部重写到可直接落库的结构。AI 只生成预览提案，不能直接改库。"
        ),
        user_prompt=user_prompt,
        schema=_story_bible_bundle_schema(),
        prompt_key="revision/story_bible_rewrite",
        prompt_version="v1",
        temperature=0.7,
    )
    story_data = raw.get("story_bible") if isinstance(raw, dict) else None
    bible = StoryBibleContract.model_validate(story_data or raw)
    normalized = novel_planner_service._normalize_story_bible(
        bible,
        project,
        payload.message,
    )
    reply = str(
        raw.get("reply") or raw.get("summary") or "已生成一份完整新版故事圣经，可预览后应用。"
    ).strip()
    patch = {
        "story_bible": normalized.model_dump(),
        "rewrite_plan": str(raw.get("summary") or raw.get("rewrite_plan") or reply),
        "impact_counts": {
            "current": _context_counts(context),
            "new": _story_bible_counts(normalized),
        },
    }
    proposal = RevisionProposalPayload(
        target_type="story_bible_bundle",
        action="update",
        title="全项目重构：新版故事圣经快照",
        patch=patch,
        reason="基于当前全局上下文生成完整新版故事圣经；应用后可接入后续大纲、场景和正文重构。",
        impact=[
            "story_bible",
            "characters",
            "world_items",
            "plot_threads",
            "chapters",
            "scenes",
            "drafts",
        ],
        is_primary=True,
        risk_notes=_text_list(
            raw.get("risk_notes") or ["全项目重构会使旧大纲、场景和正文与新版设定不再一致。"]
        ),
    )
    return reply, [proposal]


async def _create_rewrite_proposal_job(
    db: DbDep,
    *,
    project_id: str,
    payload: RevisionChatRequest,
    session_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
) -> GenerationJob:
    return await generation_service.create_revision_rewrite_proposal_job(
        db,
        user,
        tenant,
        project_id=project_id,
        revision_session_id=session_id,
        message=payload.message,
        scope=payload.scope,
        target_type=payload.target_type,
        target_id=payload.target_id,
        estimate_words=3000,
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
    logger.info(
        "revision_chat_started project_id=%s user_id=%s scope=%s target_type=%s mode=%s",
        project_id,
        user.id,
        payload.scope,
        payload.target_type,
        payload.mode,
    )
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

    if payload.mode == "full_project_rewrite":
        try:
            job = await _create_rewrite_proposal_job(
                db,
                project_id=project_id,
                payload=payload,
                session_id=session.id,
                tenant=tenant,
                user=user,
            )
            await db.refresh(job)
            job_response = GenerationJobResponse.model_validate(job)
            await db.commit()
        except Exception:
            db.sync_session.info.pop("after_commit_tasks", None)
            await db.rollback()
            raise

        messages = await message_repo.list(
            organization_id=tenant.organization_id,
            session_id=session.id,
            limit=20,
            order_by=asc(RevisionMessage.created_at),
        )
        return RevisionChatResponse(
            session=session,
            reply="已提交后台任务生成完整故事圣经快照；完成后会显示可应用提案。",
            messages=list(messages),
            proposals=[],
            job=job_response,
        )

    context = await _load_context(db, organization_id=tenant.organization_id, project=project)
    try:
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
        raw = await asyncio.wait_for(
            model_gateway.generate_json(
                db,
                organization_id=tenant.organization_id,
                project_id=project_id,
                job_id=None,
                task_type="revise_story_bible",
                system_prompt=(
                    "你是专业长篇小说设定编辑。请基于全局上下文（故事圣经、人物、世界观、"
                    "剧情线、章节大纲）与作者共创优化方案。focus.scope / focus.target_type / "
                    "focus.target_id 是本轮优化重点，但必须检查联动影响。必须只输出 JSON；"
                    "不要直接改库。proposals 是可应用的结构化修改提案：每个 proposals[] 必须"
                    "包含 target_type、action、title、patch、reason；patch 的 key 只能使用对应"
                    "目标允许字段。核心设定优化必须生成 story_bible patch，"
                    "不能只写 world_item。如果一次优化会影响多个模块，相关 proposals "
                    "必须使用同一个 group_id，并填写 group_title、is_primary、risk_notes；"
                    "用户会成组确认。target_id 必须优先使用上下文里的真实 id；"
                    "新增角色、世界观或剧情线时 action=create 且 target_id=null。"
                    "chapter 只允许 update 已有章节，只能改 title、summary、goal、conflict、"
                    "ending_hook、status；V1 不创建、不删除、不重排章节。不要输出 problem、"
                    "core_adjustment、application_notes 这类只供阅读、不能落库的字段；"
                    "如果你已经产生建议型字段，必须把它们转换成 target_type + patch。"
                ),
                user_prompt=user_prompt,
                schema=_proposal_schema(),
                prompt_key="revision/story_bible_copilot",
                prompt_version="v2",
                temperature=0.5,
            ),
            timeout=REVISION_MODEL_TIMEOUT_SECONDS,
        )
        reply, proposals = _normalize_proposals(
            raw,
            context=context,
            focus_target_type=payload.target_type,
            focus_target_id=payload.target_id,
        )
    except TimeoutError as exc:
        logger.warning("revision_chat_model_timeout project_id=%s", project_id, exc_info=True)
        await db.rollback()
        raise ConflictError(
            "AI 优化请求超时，未生成可应用修改。请缩小要求或稍后重试。",
            code="revision_model_timeout",
        ) from exc
    except Exception as exc:
        logger.warning("revision_chat_model_failed project_id=%s", project_id, exc_info=True)
        await db.rollback()
        raise ConflictError(
            "AI 优化失败，未生成可应用修改。请稍后重试或检查模型配置。",
            code="revision_model_failed",
            details={"reason": str(exc)[:500]},
        ) from exc
    logger.info(
        "revision_chat_completed project_id=%s session_id=%s proposals=%s",
        project_id,
        session.id,
        len(proposals),
    )
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
    _require_effective_patch(values)
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
    _require_effective_patch(values)
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
    patch_values = _filter_patch(patch, fields)
    if action != "create":
        _require_effective_patch(patch_values)
    values = {**defaults, **patch_values}
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
    for key, value in patch_values.items():
        setattr(entity, key, value)
    after = _public_row(entity, fields | {"id"})
    return before, after, entity.id


async def _apply_character_patch(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
    target_id: str | None,
    action: str,
    patch: dict[str, Any],
    reason: str,
    user_id: str,
) -> tuple[dict, dict, str]:
    values = _filter_patch(patch, CHARACTER_FIELDS)
    repo = CharacterRepository(db)
    if action == "create":
        _require_effective_patch(values)
        create_values = {"name": "未命名角色", **values}
        entity = await repo.create(
            organization_id=organization_id,
            project_id=project_id,
            **create_values,
        )
        return {}, _public_row(entity, CHARACTER_FIELDS | {"id"}), entity.id
    if not target_id:
        raise NotFoundError("character_not_found", code="character_not_found")
    entity = await repo.get(target_id, organization_id=organization_id)
    if not entity or entity.project_id != project_id:
        raise NotFoundError("character_not_found", code="character_not_found")

    _require_effective_patch(values)
    before = _public_row(entity, CHARACTER_FIELDS | {"id"})
    for field, value in values.items():
        revision = await character_tracker.record_copilot_proposal(
            db,
            character=entity,
            field=field,
            new_value=value,
            reason=reason,
            created_by=user_id,
        )
        if revision is not None:
            await character_tracker.apply_revision(
                db,
                revision_id=revision.id,
                organization_id=organization_id,
                applied_by=user_id,
            )
    after = _public_row(entity, CHARACTER_FIELDS | {"id"})
    return before, after, entity.id


async def _apply_chapter_patch(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
    target_id: str | None,
    action: str,
    patch: dict[str, Any],
) -> tuple[dict, dict, str]:
    if action != "update":
        raise ConflictError("chapter_revision_only_update", code="chapter_revision_only_update")
    if not target_id:
        raise NotFoundError("chapter_not_found", code="chapter_not_found")

    chapter = await ChapterRepository(db).get(target_id, organization_id=organization_id)
    if not chapter or chapter.project_id != project_id:
        raise NotFoundError("chapter_not_found", code="chapter_not_found")

    existing_scenes = await SceneRepository(db).list(
        organization_id=organization_id,
        project_id=project_id,
        chapter_id=target_id,
        limit=1,
    )
    if existing_scenes:
        raise ConflictError(
            "该章节已有场景或正文，不能自动应用大纲修改；请手动调整或重新生成场景。",
            code="chapter_has_scenes",
        )

    values = _filter_patch(patch, CHAPTER_FIELDS)
    _require_effective_patch(values)
    before = _public_row(chapter, CHAPTER_FIELDS | {"id", "chapter_index"})
    for key, value in values.items():
        setattr(chapter, key, value)
    after = _public_row(chapter, CHAPTER_FIELDS | {"id", "chapter_index"})
    return before, after, chapter.id


async def _count_rows(
    db: DbDep,
    model: type,
    *,
    organization_id: str,
    project_id: str,
    **filters: Any,
) -> int:
    stmt = (
        select(func.count())
        .select_from(model)
        .where(
            model.organization_id == organization_id,
            model.project_id == project_id,
        )
    )
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    return int((await db.execute(stmt)).scalar_one())


async def _delete_rows(
    db: DbDep,
    model: type,
    *,
    organization_id: str,
    project_id: str,
    **filters: Any,
) -> int:
    stmt = select(model).where(
        model.organization_id == organization_id,
        model.project_id == project_id,
    )
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    rows = list((await db.execute(stmt)).scalars().all())
    for row in rows:
        await db.delete(row)
    if rows:
        await db.flush()
    return len(rows)


async def _story_bible_snapshot(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
) -> dict[str, Any]:
    spec = await NovelSpecRepository(db).get_by(
        organization_id=organization_id,
        project_id=project_id,
    )
    characters = await CharacterRepository(db).list(
        organization_id=organization_id,
        project_id=project_id,
        limit=200,
    )
    world_items = await WorldItemRepository(db).list(
        organization_id=organization_id,
        project_id=project_id,
        limit=200,
    )
    plot_threads = await PlotThreadRepository(db).list(
        organization_id=organization_id,
        project_id=project_id,
        limit=200,
    )
    return {
        "story_bible": None if not spec else _public_row(spec, SPEC_FIELDS | {"id"}),
        "characters": [_public_row(row, CHARACTER_FIELDS | {"id"}) for row in characters],
        "world_items": [_public_row(row, WORLD_ITEM_FIELDS | {"id"}) for row in world_items],
        "plot_threads": [_public_row(row, PLOT_THREAD_FIELDS | {"id"}) for row in plot_threads],
        "counts": {
            "chapters": await _count_rows(
                db,
                Chapter,
                organization_id=organization_id,
                project_id=project_id,
            ),
            "scenes": await _count_rows(
                db,
                Scene,
                organization_id=organization_id,
                project_id=project_id,
            ),
            "draft_versions": await _count_rows(
                db,
                DraftVersion,
                organization_id=organization_id,
                project_id=project_id,
            ),
            "continuity_issues": await _count_rows(
                db,
                ContinuityIssue,
                organization_id=organization_id,
                project_id=project_id,
            ),
            "scene_memory_entries": await _count_rows(
                db,
                MemoryEntry,
                organization_id=organization_id,
                project_id=project_id,
                source_type="scene",
            ),
        },
    }


async def _clear_outline_dependents_for_revision(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model, key in [
        (ContinuityIssue, "continuity_issues"),
        (DraftVersion, "draft_versions"),
        (Scene, "scenes"),
        (Chapter, "chapters"),
    ]:
        counts[key] = await _delete_rows(
            db,
            model,
            organization_id=organization_id,
            project_id=project_id,
        )
    counts["scene_memory_entries"] = await _delete_rows(
        db,
        MemoryEntry,
        organization_id=organization_id,
        project_id=project_id,
        source_type="scene",
    )
    return counts


async def _replace_story_bible_assets(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
    bible: StoryBibleContract,
) -> dict[str, int]:
    # 先删版本链，避免旧资产被替换后留下孤儿记录。
    for model in [
        PlotThreadRevision,
        WorldItemRevision,
        CharacterRevision,
        PlotThread,
        WorldItem,
        Character,
    ]:
        await _delete_rows(
            db,
            model,
            organization_id=organization_id,
            project_id=project_id,
        )

    character_count = 0
    for seed in bible.main_characters or []:
        name = (seed.name or "").strip()
        if not name:
            continue
        await CharacterRepository(db).create(
            organization_id=organization_id,
            project_id=project_id,
            name=name,
            role=seed.role or "supporting",
            description=seed.description,
            personality=seed.personality,
            motivation=seed.motivation,
            secret=seed.secret,
            arc=seed.arc,
            relationships=seed.relationships,
            current_state=seed.current_state,
        )
        character_count += 1

    world_count = 0

    async def create_world_item(
        *,
        item_type: str,
        name: str,
        description: str,
        importance: str = "medium",
        is_hard_rule: bool = False,
    ) -> None:
        nonlocal world_count
        clean_name = name.strip()[:200]
        clean_description = description.strip()
        if not clean_name and not clean_description:
            return
        await WorldItemRepository(db).create(
            organization_id=organization_id,
            project_id=project_id,
            type=item_type,
            name=clean_name or clean_description[:80] or "未命名设定",
            description=clean_description or clean_name,
            rules={"source": "story_bible_bundle", "kind": item_type},
            related_characters=[],
            importance=importance or "medium",
            is_hard_rule=is_hard_rule,
        )
        world_count += 1

    for index, location in enumerate(bible.locations or [], start=1):
        await create_world_item(
            item_type="location",
            name=location.name or f"重要地点 {index}",
            description=location.description or location.name,
            importance=location.importance,
        )
    for index, faction in enumerate(bible.factions or [], start=1):
        await create_world_item(
            item_type="faction",
            name=faction.name or f"关键势力 {index}",
            description=faction.description or faction.name,
            importance=faction.importance,
        )
    for index, rule in enumerate(bible.world_rules or [], start=1):
        text = str(rule).strip()
        if text:
            await create_world_item(
                item_type="rule",
                name=text[:80] or f"世界规则 {index}",
                description=text,
                importance="high",
                is_hard_rule=True,
            )

    plot_thread_count = 0
    threads = list(bible.plot_threads or []) or [bible.theme or bible.premise]
    for index, thread in enumerate(threads, start=1):
        title = str(thread).strip()
        if not title:
            continue
        await PlotThreadRepository(db).create(
            organization_id=organization_id,
            project_id=project_id,
            title=title[:200],
            thread_type="main" if index == 1 else "subplot",
            description=title,
            status="open",
            related_characters=[],
            opened_at_scene_id=None,
            closed_at_scene_id=None,
        )
        plot_thread_count += 1

    return {
        "characters": character_count,
        "world_items": world_count,
        "plot_threads": plot_thread_count,
    }


async def _apply_story_bible_bundle_patch(
    db: DbDep,
    *,
    project: Project,
    organization_id: str,
    patch: dict[str, Any],
    clear_dependents: bool,
) -> tuple[dict, dict, str]:
    story_bible = patch.get("story_bible") if isinstance(patch, dict) else None
    if not isinstance(story_bible, dict):
        raise ConflictError("story_bible_bundle_invalid", code="story_bible_bundle_invalid")

    bible = novel_planner_service._normalize_story_bible(
        StoryBibleContract.model_validate(story_bible),
        project,
        story_bible.get("premise") or project.title,
    )
    before = await _story_bible_snapshot(
        db,
        organization_id=organization_id,
        project_id=project.id,
    )

    spec_repo = NovelSpecRepository(db)
    spec = await spec_repo.get_by(
        organization_id=organization_id,
        project_id=project.id,
    )
    values = {
        "premise": bible.premise,
        "theme": bible.theme,
        "genre": bible.genre,
        "tone": bible.tone,
        "target_reader": bible.target_reader,
        "narrative_pov": bible.narrative_pov,
        "style_guide": bible.style_guide,
        "constraints": list(bible.constraints or []),
        "continuity_rules": list(bible.continuity_rules or []),
    }
    if spec is None:
        spec = await spec_repo.create(
            organization_id=organization_id,
            project_id=project.id,
            **values,
        )
    else:
        for key, value in values.items():
            setattr(spec, key, value)

    project.genre = bible.genre or project.genre
    project.target_reader = bible.target_reader or project.target_reader
    project.style = (bible.style_guide or project.style)[:500]
    project.status = "bible_ready"

    clear_counts = {}
    if clear_dependents:
        clear_counts = await _clear_outline_dependents_for_revision(
            db,
            organization_id=organization_id,
            project_id=project.id,
        )
    asset_counts = await _replace_story_bible_assets(
        db,
        organization_id=organization_id,
        project_id=project.id,
        bible=bible,
    )
    await db.flush()
    after = await _story_bible_snapshot(
        db,
        organization_id=organization_id,
        project_id=project.id,
    )
    after["applied_counts"] = {
        "cleared": clear_counts,
        "assets": asset_counts,
    }
    return before, after, spec.id


async def _ensure_no_active_generation_jobs(
    db: DbDep,
    *,
    organization_id: str,
    project_id: str,
) -> None:
    active = (
        await db.execute(
            select(GenerationJob)
            .where(
                GenerationJob.organization_id == organization_id,
                GenerationJob.project_id == project_id,
                GenerationJob.status.in_(["queued", "running"]),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if active:
        raise ConflictError(
            "项目已有运行中的生成任务，请等待完成后再应用并重构。",
            code="project_has_active_job",
            details={"job_id": active.id, "job_type": active.job_type},
        )


async def _apply_proposal_change(
    db: DbDep,
    *,
    proposal: RevisionProposal,
    project: Project,
    organization_id: str,
    user_id: str,
) -> RevisionAppliedChange:
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
            organization_id=organization_id,
            project_id=project.id,
            patch=proposal.patch,
        )
    elif target_type == "character":
        before, after, target_id = await _apply_character_patch(
            db,
            organization_id=organization_id,
            project_id=project.id,
            target_id=proposal.target_id,
            action=proposal.action,
            patch=proposal.patch,
            reason=proposal.reason,
            user_id=user_id,
        )
    elif target_type == "world_item":
        before, after, target_id = await _apply_entity_patch(
            db,
            repo=WorldItemRepository(db),
            model_name="world_item",
            organization_id=organization_id,
            project_id=project.id,
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
            organization_id=organization_id,
            project_id=project.id,
            target_id=proposal.target_id,
            action=proposal.action,
            patch=proposal.patch,
            fields=PLOT_THREAD_FIELDS,
            defaults={"title": "未命名剧情线"},
        )
    elif target_type == "chapter":
        before, after, target_id = await _apply_chapter_patch(
            db,
            organization_id=organization_id,
            project_id=project.id,
            target_id=proposal.target_id,
            action=proposal.action,
            patch=proposal.patch,
        )
    elif target_type == "story_bible_bundle":
        before, after, target_id = await _apply_story_bible_bundle_patch(
            db,
            project=project,
            organization_id=organization_id,
            patch=proposal.patch,
            clear_dependents=False,
        )
    else:
        raise ConflictError("revision_target_not_supported", code="revision_target_not_supported")

    proposal.status = "applied"
    proposal.target_id = target_id
    await db.flush()
    return await RevisionAppliedChangeRepository(db).create(
        organization_id=organization_id,
        project_id=project.id,
        session_id=proposal.session_id,
        proposal_id=proposal.id,
        target_type=proposal.target_type,
        target_id=target_id,
        before_data=before,
        after_data=after,
        applied_by=user_id,
    )


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
    change = await _apply_proposal_change(
        db,
        proposal=proposal,
        project=project,
        organization_id=tenant.organization_id,
        user_id=user.id,
    )
    await db.commit()
    return ApplyProposalResponse(proposal=proposal, applied_change_id=change.id)


@router.post(
    "/proposals/{proposal_id}/apply-with-rebuild",
    response_model=ApplyProposalWithRebuildResponse,
)
async def apply_revision_proposal_with_rebuild(
    project_id: str,
    proposal_id: str,
    payload: ApplyProposalWithRebuildRequest,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    project = await _ensure_project(project_id, tenant, db)
    proposal = await RevisionProposalRepository(db).get(
        proposal_id,
        organization_id=tenant.organization_id,
    )
    if not proposal or proposal.project_id != project_id:
        raise NotFoundError("revision_proposal_not_found", code="revision_proposal_not_found")
    if proposal.target_type != "story_bible_bundle":
        raise ConflictError(
            "只有完整故事圣经快照提案支持应用并重构项目。",
            code="revision_rebuild_requires_bundle",
        )
    if proposal.status == "applied":
        raise ConflictError(
            "revision_proposal_already_applied",
            code="revision_proposal_already_applied",
        )

    await _ensure_no_active_generation_jobs(
        db,
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    try:
        job = await generation_service.create_full_novel_job(
            db,
            user,
            tenant,
            project_id=project_id,
            estimate_words=payload.estimate_words,
            mode="full_novel",
            topic=payload.topic or proposal.title,
            target_chapters=payload.target_chapters,
            scenes_per_chapter=payload.scenes_per_chapter,
            write_drafts=payload.write_drafts,
            force_regenerate_spec=False,
            force_regenerate_outline=True,
            force_regenerate_scenes=True,
            force_regenerate_drafts=True,
            require_full_novel_entitlement=False,
        )
        before, after, target_id = await _apply_story_bible_bundle_patch(
            db,
            project=project,
            organization_id=tenant.organization_id,
            patch=proposal.patch,
            clear_dependents=True,
        )
        proposal.status = "applied"
        proposal.target_id = target_id
        await db.flush()
        change = await RevisionAppliedChangeRepository(db).create(
            organization_id=tenant.organization_id,
            project_id=project.id,
            session_id=proposal.session_id,
            proposal_id=proposal.id,
            target_type=proposal.target_type,
            target_id=target_id,
            before_data=before,
            after_data=after,
            applied_by=user.id,
        )
        await db.refresh(job)
        job_response = GenerationJobResponse.model_validate(job)
        await db.commit()
    except Exception:
        db.sync_session.info.pop("after_commit_tasks", None)
        await db.rollback()
        raise

    return ApplyProposalWithRebuildResponse(
        proposal=proposal,
        applied_change_id=change.id,
        job=job_response,
    )


@router.post(
    "/proposal-groups/{group_id}/apply",
    response_model=ApplyProposalGroupResponse,
)
async def apply_revision_proposal_group(
    project_id: str,
    group_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    project = await _ensure_project(project_id, tenant, db)
    if not group_id.strip():
        raise NotFoundError(
            "revision_proposal_group_not_found",
            code="revision_proposal_group_not_found",
        )

    proposals = await RevisionProposalRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
        group_id=group_id,
        status="pending",
        order_by=asc(RevisionProposal.created_at),
    )
    if not proposals:
        raise NotFoundError(
            "revision_proposal_group_not_found",
            code="revision_proposal_group_not_found",
        )

    try:
        changes = []
        for proposal in proposals:
            changes.append(
                await _apply_proposal_change(
                    db,
                    proposal=proposal,
                    project=project,
                    organization_id=tenant.organization_id,
                    user_id=user.id,
                )
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return ApplyProposalGroupResponse(
        proposals=list(proposals),
        applied_change_ids=[change.id for change in changes],
    )
