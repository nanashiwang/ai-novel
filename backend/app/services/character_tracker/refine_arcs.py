"""Outline 完成后基于章节大纲精细化人物 motivation / arc / secret。

Sprint 11 Phase E：让 Bible 阶段只生成 v0 草稿（驱动力方向 / 成长方向 / 秘密类型），
等章节大纲产出后再用三幕结构对齐 motivation/arc/secret 三个字段的具体内容。

调用流程：
GenerateOutlineWorkflow 主 activity 完成后 fire-and-forget 调本模块的
extract_character_arcs_from_outline；失败不影响主流程（outline 已 succeeded）。

产出落 character_revisions（source='ai_arc_refine' status='pending'）等用户审核。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.character import Character
from app.models.project import NovelSpec
from app.repositories import (
    CharacterRepository,
    NovelSpecRepository,
)
from app.services.character_tracker import character_tracker
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_logger = logging.getLogger(__name__)

_PROMPT_KEY = "character/refine_arcs"
_PROMPT_VERSION = "v1"
_ALLOWED_FIELDS = {"motivation", "arc", "secret"}

_REFINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "refinements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "character_name": {"type": "string"},
                    "field": {"type": "string", "enum": sorted(_ALLOWED_FIELDS)},
                    "new_value": {"type": "string", "maxLength": 600},
                    "reason": {"type": "string", "maxLength": 200},
                },
                "required": ["character_name", "field", "new_value"],
            },
        }
    },
    "required": ["refinements"],
}


def _chapters_brief(chapters: list[Chapter]) -> list[dict[str, Any]]:
    return [
        {
            "chapter_index": c.chapter_index,
            "title": c.title,
            "goal": c.goal,
            "conflict": c.conflict,
            "ending_hook": c.ending_hook,
            "summary": c.summary,
        }
        for c in chapters
    ]


def _characters_brief(characters: list[Character]) -> list[dict[str, Any]]:
    return [
        {
            "name": c.name,
            "role": c.role,
            "description": c.description,
            "personality": c.personality,
            "motivation": c.motivation,
            "arc": c.arc,
            "secret": c.secret,
        }
        for c in characters
    ]


def _spec_brief(spec: NovelSpec | None) -> dict[str, str]:
    if not spec:
        return {}
    return {
        "premise": spec.premise or "",
        "theme": spec.theme or "",
        "tone": spec.tone or "",
        "narrative_pov": spec.narrative_pov or "",
    }


async def extract_character_arcs_from_outline(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    created_by: str,
) -> int:
    """主入口：基于已生成的 chapters 精细化所有 character 的 motivation / arc / secret。

    返回成功落库的 revision 数；任何失败 swallow + warn（fire-and-forget）。
    """
    chap_stmt = (
        select(Chapter)
        .where(
            Chapter.organization_id == organization_id,
            Chapter.project_id == project_id,
        )
        .order_by(Chapter.chapter_index.asc())
    )
    chapters = list((await session.execute(chap_stmt)).scalars().all())
    if not chapters:
        return 0

    characters = list(
        await CharacterRepository(session).list(
            organization_id=organization_id,
            project_id=project_id,
            limit=40,
        )
    )
    if not characters:
        return 0

    spec = await NovelSpecRepository(session).get_by(
        organization_id=organization_id,
        project_id=project_id,
    )

    name_to_character = {c.name: c for c in characters}
    user_prompt = (
        "## story_spec\n"
        f"{_spec_brief(spec)}\n\n"
        "## chapters\n"
        f"{_chapters_brief(chapters)}\n\n"
        "## characters_v0\n"
        f"{_characters_brief(characters)}\n"
    )

    try:
        system_prompt = prompt_manager.load(
            _PROMPT_KEY, version=_PROMPT_VERSION, strict=False
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=None,
            task_type="refine_character_arcs",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=_REFINE_SCHEMA,
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            temperature=0.4,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("refine_character_arcs model_call_failed: %s", exc)
        return 0

    refinements = raw.get("refinements") if isinstance(raw, dict) else None
    if not isinstance(refinements, list):
        return 0

    written = 0
    for item in refinements:
        if not isinstance(item, dict):
            continue
        name = (item.get("character_name") or "").strip()
        field = (item.get("field") or "").strip()
        new_value = item.get("new_value")
        reason = (item.get("reason") or "").strip()
        if field not in _ALLOWED_FIELDS:
            continue
        if not isinstance(new_value, str) or not new_value.strip():
            continue
        character = name_to_character.get(name)
        if not character:
            continue
        try:
            await character_tracker.record_arc_refinement(
                session,
                character=character,
                field=field,
                new_value=new_value.strip(),
                reason=reason,
                created_by=created_by,
            )
            written += 1
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "refine_character_arcs record_failed name=%s field=%s err=%s",
                name,
                field,
                exc,
            )
    return written
