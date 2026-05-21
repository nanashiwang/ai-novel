"""AI 自动推演角色状态变化。

write_scene / rewrite_scene workflow 完成后异步调用，从场景正文反推
角色字段变化，落 character_revisions（source='ai_inferred' status='pending'）。

设计：fire-and-forget。失败不影响主流程（scene 已保存），仅打日志。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.repositories import CharacterRepository
from app.services.character_tracker import (
    CHARACTER_REVISION_FIELDS,
    character_tracker,
)
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_logger = logging.getLogger(__name__)

_PROMPT_KEY = "character/extract_state"
_PROMPT_VERSION = "v1"

_EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "character_name": {"type": "string"},
                    "field": {
                        "type": "string",
                        "enum": sorted(CHARACTER_REVISION_FIELDS),
                    },
                    "new_value": {
                        # 允许 string | object，落库时按字段类型适配
                        "anyOf": [
                            {"type": "string"},
                            {"type": "object"},
                            {"type": "null"},
                        ]
                    },
                    "evidence": {"type": "string", "maxLength": 240},
                },
                "required": ["character_name", "field", "new_value"],
            },
        }
    },
    "required": ["changes"],
}


def _characters_brief(characters: list[Character]) -> list[dict[str, Any]]:
    """给 prompt 用的紧凑角色卡。"""
    out: list[dict[str, Any]] = []
    for c in characters:
        out.append(
            {
                "name": c.name,
                "role": c.role,
                "description": c.description,
                "personality": c.personality,
                "motivation": c.motivation,
                "secret": c.secret,
                "arc": c.arc,
                "current_state": c.current_state or {},
                "relationships": c.relationships or {},
            }
        )
    return out


async def extract_state_changes_from_scene(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    scene_id: str,
    scene_content: str,
    created_by: str,
) -> int:
    """对一段场景正文调用 LLM 抽取角色状态变化并落库为 pending revision。

    返回成功落库的 revision 数量；任何失败一律 swallow + warn（fire-and-forget）。
    """
    if not scene_content.strip():
        return 0
    chars = list(
        await CharacterRepository(session).list(
            organization_id=organization_id,
            project_id=project_id,
            limit=40,
        )
    )
    if not chars:
        return 0
    name_to_character = {c.name: c for c in chars}

    user_prompt = (
        "## 当前角色卡\n"
        f"{_characters_brief(chars)}\n\n"
        "## scene 正文\n"
        f"{scene_content}\n"
    )

    try:
        system_prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION, strict=False)
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=None,
            task_type="extract_character_state",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=_EXTRACT_SCHEMA,
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("extract_character_state model_call_failed: %s", exc)
        return 0

    changes = raw.get("changes") if isinstance(raw, dict) else None
    if not isinstance(changes, list):
        return 0

    written = 0
    for change in changes:
        if not isinstance(change, dict):
            continue
        name = (change.get("character_name") or "").strip()
        field = (change.get("field") or "").strip()
        new_value = change.get("new_value")
        evidence = (change.get("evidence") or "").strip()
        if field not in CHARACTER_REVISION_FIELDS:
            continue
        character = name_to_character.get(name)
        if not character:
            continue
        # 字段类型适配：字符串字段需要 str；JSON 字段需要 dict
        new_value = _coerce_field_value(field, new_value)
        if new_value is None:
            continue
        try:
            await character_tracker.record_ai_inferred(
                session,
                character=character,
                field=field,
                new_value=new_value,
                reason=evidence,
                scene_id=scene_id,
                created_by=created_by,
            )
            written += 1
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "extract_character_state record_failed name=%s field=%s err=%s",
                name,
                field,
                exc,
            )
    return written


_TEXT_FIELDS = {"name", "role", "description", "personality", "motivation", "secret", "arc"}
_JSON_FIELDS = {"relationships", "current_state"}


def _coerce_field_value(field: str, value: Any) -> Any:
    """把 LLM 输出适配为目标字段类型；不合法返回 None。"""
    if field in _TEXT_FIELDS:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, (int, float, bool)):
            return str(value)
        return None
    if field in _JSON_FIELDS:
        if isinstance(value, dict):
            return value
        return None
    return None
