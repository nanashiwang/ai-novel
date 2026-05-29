from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.scene import Scene
from app.models.story_state_item import StoryStateItem
from app.repositories import (
    ChapterStateRequirementRepository,
    StoryStateRepository,
)
from app.services.context_builder.service import context_builder

AntiForgettingPurpose = Literal["writing", "audit"]


async def build_anti_forgetting_prompt_block(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    chapter: Chapter,
    scene: Scene,
    purpose: AntiForgettingPurpose,
    state_limit: int = 18,
    requirement_limit: int = 10,
) -> tuple[str, dict[str, Any]]:
    """Build a compact anti-forgetting block for generation or audit.

    ContextBuilder already injects story_states as regular context. This helper
    repeats the highest-risk state facts as an explicit checklist so write,
    rewrite, and audit stages apply the same state budget and ids.
    """
    meta: dict[str, Any] = {
        "anti_forgetting_state_count": 0,
        "anti_forgetting_requirement_count": 0,
    }
    try:
        state_repo = StoryStateRepository(session)
        req_repo = ChapterStateRequirementRepository(session)
        state_rows = list(
            await state_repo.list_filtered(
                organization_id=organization_id,
                project_id=project_id,
                limit=max(state_limit * 4, 60),
            )
        )
        requirement_rows = list(
            await req_repo.list_for_chapter(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter.id,
            )
        )[:requirement_limit]
    except Exception:  # noqa: BLE001 - Anti-forgetting must not block main flow.
        return "", meta

    if not state_rows and not requirement_rows:
        return "", meta

    chapter_index_by_id = await _chapter_index_by_id(session, state_rows)
    focus_names = {name.strip() for name in (scene.characters or []) if name and name.strip()}
    ranked = list(
        context_builder._select_story_state_items(
            state_rows,
            current_chapter_index=chapter.chapter_index,
            chapter_index_by_id=chapter_index_by_id,
            focus_names=focus_names,
            limit=state_limit,
        )
    )

    required_state_ids = {req.state_item_id for req in requirement_rows if req.state_item_id}
    ranked_ids = {item.id for item in ranked}
    required_items = [
        item for item in state_rows if item.id in required_state_ids and item.id not in ranked_ids
    ]
    if required_items:
        ranked = (required_items + ranked)[: max(state_limit, len(required_items))]

    if purpose == "audit":
        lines = _audit_header()
        requirement_title = "\n本章承接要求（必须检查正文是否承接、推进或合理悬置）："
        state_title = "\n关键状态项（用于检查前后矛盾、提前使用、遗忘承接）："
    else:
        lines = _writing_header()
        requirement_title = "\n本章承接要求（生成时必须自然承接、推进或合理悬置）："
        state_title = "\n关键状态项（生成时必须保持一致）："

    if requirement_rows:
        lines.append(requirement_title)
        for req in requirement_rows:
            lines.append(
                f"· requirement_id={req.id}；story_state_item_id={req.state_item_id}；"
                f"[{req.requirement_type}] P{int(req.priority or 0)}：{req.summary}"
            )

    if ranked:
        lines.append(state_title)
        for item in ranked:
            lines.append(_format_state_item(item, chapter_index_by_id))

    meta["anti_forgetting_state_count"] = len(ranked)
    meta["anti_forgetting_requirement_count"] = len(requirement_rows)
    return "\n".join(lines), meta


async def load_story_state_items_by_id(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    state_item_ids: set[str],
) -> dict[str, StoryStateItem]:
    if not state_item_ids:
        return {}
    rows = (
        await session.execute(
            select(StoryStateItem).where(
                StoryStateItem.organization_id == organization_id,
                StoryStateItem.project_id == project_id,
                StoryStateItem.id.in_(state_item_ids),
            )
        )
    ).scalars().all()
    return {row.id: row for row in rows}


def format_story_state_brief(item: StoryStateItem) -> str:
    prefix = "[硬约束] " if item.is_hard_constraint else ""
    payload = context_builder._stringify_value(item.value_json or {})
    detail = f"；细节={payload}" if payload and payload != "{}" else ""
    return (
        f"{prefix}[{item.entity_type}/{item.state_type}] {item.name}；"
        f"status={item.status or 'active'}；P{int(item.priority or 0)}："
        f"{item.summary or '—'}{detail}"
    )


async def _chapter_index_by_id(
    session: AsyncSession,
    state_rows: list[StoryStateItem],
) -> dict[str, int]:
    chapter_ids = {
        chapter_ref
        for item in state_rows
        for chapter_ref in (item.source_chapter_id, item.updated_in_chapter_id)
        if chapter_ref
    }
    if not chapter_ids:
        return {}
    try:
        rows = (
            await session.execute(
                select(Chapter.id, Chapter.chapter_index).where(Chapter.id.in_(chapter_ids))
            )
        ).all()
    except Exception:  # noqa: BLE001
        return {}
    return {row[0]: int(row[1] or 0) for row in rows}


def _audit_header() -> list[str]:
    return [
        "\n\n## 防遗忘审稿清单",
        "判定规则：只基于本清单、ContextBuilder 上下文和待审稿正文里的明示内容判定；"
        "不要凭空增加正文必须出现的设定。",
        "若发现正文与某条关键状态或本章承接要求冲突，请优先使用 "
        "state_conflict / forgotten_state / premature_state_use / "
        "resolved_state_reused / hard_constraint_violation。",
    ]


def _writing_header() -> list[str]:
    return [
        "\n\n## 写作防遗忘承接清单",
        "生成规则：这是本场生成前必须遵守的状态清单；它的优先级高于普通上下文摘要。",
        "写作时必须保持关键状态一致：damaged/consumed/resolved/inactive 等状态，"
        "不得被写成仍可正常使用，除非当前场景任务明确写出修复、重新获得或重新激活过程。",
        "标记为[硬约束]的状态不得改写；本章承接要求必须自然进入剧情、动作、对白或内心，"
        "不能作为清单、编号、解释性旁白输出。",
        "正文中禁止输出 story_state_item_id、requirement_id、清单标题或任何审稿/检查说明。",
    ]


def _format_state_item(
    item: StoryStateItem,
    chapter_index_by_id: dict[str, int],
) -> str:
    source_index = chapter_index_by_id.get(
        item.updated_in_chapter_id or item.source_chapter_id or "",
        0,
    )
    source = f"；来源章=第{source_index}章" if source_index else ""
    return f"· story_state_item_id={item.id}；{format_story_state_brief(item)}{source}"
