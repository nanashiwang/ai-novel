"""角色里程碑快照（Sprint 17-A 防漂移）。

每 50 章为每个角色生成 1 条 milestone snapshot 行（character_revisions
中 field='_milestone'、milestone_chapter_index 非 NULL）。

ContextBuilder._fmt_character_actions 优先读最近 milestone 作为基线，
再叠加 milestone 之后的少量普通 revision，从而避免 1000 章后 prompt
里堆积无穷的流水状态导致漂移。

接口：create_milestones_for_project(session, organization_id, project_id,
chapter_index) — 给该项目所有角色批量生成快照。失败 swallow，不阻断。
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.character_revision import CharacterRevision
from app.repositories import CharacterRepository
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_KEY = "character/milestone_snapshot"
_PROMPT_VERSION = "v1"
_MILESTONE_FIELD = "_milestone"
_logger = logging.getLogger(__name__)


def _new_id() -> str:
    return "charrev_" + secrets.token_hex(8)


async def _recent_applied_revisions(
    session: AsyncSession,
    *,
    organization_id: str,
    character_id: str,
    since_chapter_index: int | None,
    limit: int = 80,
) -> list[CharacterRevision]:
    """拉该角色最近 applied 的流水 revision（排除 milestone 行）。"""
    stmt = (
        select(CharacterRevision)
        .where(
            CharacterRevision.organization_id == organization_id,
            CharacterRevision.character_id == character_id,
            CharacterRevision.status == "applied",
            CharacterRevision.milestone_chapter_index.is_(None),
            CharacterRevision.field != _MILESTONE_FIELD,
        )
        .order_by(desc(CharacterRevision.created_at))
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return rows


def _format_revision_for_prompt(rev: CharacterRevision) -> str:
    old = json.dumps(rev.old_value, ensure_ascii=False) if rev.old_value is not None else "—"
    new = json.dumps(rev.new_value, ensure_ascii=False) if rev.new_value is not None else "—"
    reason = (rev.reason or "")[:120]
    return f"- {rev.field}：{old} → {new}（reason: {reason}）"


async def create_milestone_for_character(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    character: Character,
    chapter_index: int,
    job_id: str | None = None,
) -> CharacterRevision | None:
    """为单个角色生成 milestone snapshot。无可用 revision 时返回 None。"""
    revisions = await _recent_applied_revisions(
        session,
        organization_id=organization_id,
        character_id=character.id,
        since_chapter_index=chapter_index - 50,
    )
    if not revisions:
        return None

    try:
        prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
    except Exception:  # noqa: BLE001
        _logger.warning("milestone_prompt_load_failed", exc_info=True)
        return None

    revs_block = "\n".join(_format_revision_for_prompt(r) for r in revisions)
    char_block = (
        f"姓名：{character.name}\n"
        f"角色：{character.role or '—'}\n"
        f"描述：{(character.description or '')[:300]}\n"
        f"性格：{(character.personality or '')[:300]}\n"
        f"动机：{(character.motivation or '')[:200]}\n"
        f"弧光：{(character.arc or '')[:200]}\n"
    )
    user_prompt = (
        f"## 角色当前权威字段\n{char_block}\n\n"
        f"## 该角色最近 50 章流水 revisions（{len(revisions)} 条）\n{revs_block}\n\n"
        f"请按契约输出截至第 {chapter_index} 章的里程碑 JSON。"
    )

    try:
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="character_milestone",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema={"type": "object"},
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "character_id": character.id,
                "chapter_index": chapter_index,
            },
        )
    except Exception:  # noqa: BLE001
        _logger.warning(
            "milestone_llm_failed",
            extra={"character_id": character.id, "chapter_index": chapter_index},
            exc_info=True,
        )
        return None

    snapshot: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if not snapshot:
        return None

    row = CharacterRevision(
        id=_new_id(),
        organization_id=organization_id,
        project_id=project_id,
        character_id=character.id,
        field=_MILESTONE_FIELD,
        old_value=None,
        new_value=snapshot,
        reason=f"自动里程碑（第 {chapter_index} 章）",
        source="ai_inferred",
        scene_id=None,
        status="applied",
        created_by="system",
        applied_by="system",
        applied_at=None,
        milestone_chapter_index=chapter_index,
    )
    session.add(row)
    await session.flush()
    return row


async def create_milestones_for_project(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    chapter_index: int,
    job_id: str | None = None,
) -> int:
    """给项目所有角色批量生成 milestone。返回成功数量。"""
    chars = list(
        await CharacterRepository(session).list(
            organization_id=organization_id,
            project_id=project_id,
        )
    )
    if not chars:
        return 0
    created = 0
    for char in chars:
        try:
            row = await create_milestone_for_character(
                session,
                organization_id=organization_id,
                project_id=project_id,
                character=char,
                chapter_index=chapter_index,
                job_id=job_id,
            )
            if row is not None:
                created += 1
        except Exception:  # noqa: BLE001
            _logger.warning(
                "milestone_per_character_failed",
                extra={"character_id": char.id, "chapter_index": chapter_index},
                exc_info=True,
            )
    return created


__all__ = [
    "create_milestone_for_character",
    "create_milestones_for_project",
]
