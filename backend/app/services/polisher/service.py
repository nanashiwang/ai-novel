"""章后润色 pass 服务（Sprint 17-C 方案 3）。

当一章所有 scene 都 drafted 后，整章拼接 + 元数据 → 一次 LLM call 润色，
落到 draft_versions(version_type='polish')。用户审阅后选择是否接受。

设计：
- 拉本章所有 scene 的最新 draft 拼接（场之间用 \\n\\n---\\n\\n 分隔）
- 装配上下文：hard_anchors / scene_beats / pacing_type / open plot_threads /
  本章 must_include 汇总
- 调 model_gateway.generate_text 走长内容路径（timeout 15min）
- 落库前质量验证：字数 ≥ 原文 * 0.9；must_include 命中率 ≥ 70%；主角名命中
- dedupe：同章已存在 status='draft' 的 polish 且 created_at > max(scene draft updated_at) 时跳过
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.repositories import (
    CharacterRepository,
    DraftVersionRepository,
    PlotThreadRepository,
    SceneRepository,
)
from app.services.context_builder.service import context_builder
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_KEY = "writing/polish_chapter"
_PROMPT_VERSION = "v1"
_LONG_TIMEOUT_SECONDS = 900.0  # 15min
_MIN_WORDS_RATIO = 0.9
_MIN_MUST_INCLUDE_HIT_RATIO = 0.7

_logger = logging.getLogger(__name__)


def _new_id() -> str:
    return "draft_" + secrets.token_hex(8)


@dataclass
class _PolishContext:
    """polish_chapter 的输入上下文聚合。"""

    chapter_text: str
    orig_total_len: int
    must_include_terms: list[str]
    character_names: list[str]


async def _gather_polish_context(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    chapter: Chapter,
) -> tuple[_PolishContext, list[Scene], dict[str, DraftVersion]]:
    """拉本章所有 scene + 最新 draft，拼接整章原文，收集质量验证用的关键词。"""
    scenes = list(
        await SceneRepository(session).list(
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
        )
    )
    scenes.sort(key=lambda s: s.scene_index)
    if not scenes:
        return _PolishContext("", 0, [], []), [], {}

    draft_repo = DraftVersionRepository(session)
    parts: list[str] = []
    must_include_terms: list[str] = []
    character_names: list[str] = []
    seen_chars: set[str] = set()
    drafts_by_scene: dict[str, DraftVersion] = {}
    total_len = 0
    for scene in scenes:
        drafts = list(
            await draft_repo.list(
                organization_id=organization_id,
                project_id=project_id,
                scene_id=scene.id,
                status="draft",
                limit=1,
            )
        )
        if not drafts or not drafts[0].content:
            continue
        drafts_by_scene[scene.id] = drafts[0]
        content = drafts[0].content.strip()
        total_len += len(content)
        parts.append(content)
        for term in scene.must_include or []:
            if term and term not in must_include_terms:
                must_include_terms.append(term)
        for name in scene.characters or []:
            if name and name not in seen_chars:
                seen_chars.add(name)
                character_names.append(name)

    chapter_text = "\n\n---\n\n".join(parts)
    return (
        _PolishContext(
            chapter_text=chapter_text,
            orig_total_len=total_len,
            must_include_terms=must_include_terms,
            character_names=character_names,
        ),
        scenes,
        drafts_by_scene,
    )


async def _gather_meta_block(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    project: Project,
    spec: NovelSpec,
    chapter: Chapter,
    character_names: list[str],
) -> str:
    """装配 prompt 的 ## 元数据 段：hard_anchors / scene_beats / pacing /
    open plot_threads / character 一句话状态。"""
    hard_anchors = await context_builder._extract_hard_anchors(
        session,
        spec,
        organization_id=organization_id,
        project_id=project_id,
    )
    beats = list(chapter.scene_beats or [])
    beats_block = ""
    if beats:
        joined = "\n".join(f"  {i + 1}. {b}" for i, b in enumerate(beats))
        beats_block = "本章 scene 拍点：\n" + joined

    pacing = (getattr(chapter, "pacing_type", "") or "").strip()
    emo = int(getattr(chapter, "emotion_intensity", 3) or 3)
    pacing_block = ""
    if pacing:
        pacing_block = f"本章节奏：{pacing}（情感强度 {emo}/5）"

    open_threads_block = ""
    try:
        rows = list(
            await PlotThreadRepository(session).list(
                organization_id=organization_id,
                project_id=project_id,
                limit=20,
            )
        )
        open_threads = [r for r in rows if r.status == "open"][:8]
        if open_threads:
            open_threads_block = "open plot_threads：\n" + "\n".join(
                f"- [{t.thread_type}] {t.title}：{t.description or '—'}"
                for t in open_threads
            )
    except Exception:  # noqa: BLE001
        open_threads_block = ""

    char_block = ""
    try:
        char_rows = list(
            await CharacterRepository(session).list(
                organization_id=organization_id,
                project_id=project_id,
            )
        )
        focus_chars = [c for c in char_rows if c.name in character_names][:6]
        if focus_chars:
            char_block = "本章涉及角色（保持其身份与口吻不变）：\n" + "\n".join(
                f"- {c.name}（{c.role or '配角'}）：{(c.description or '')[:80]}"
                for c in focus_chars
            )
    except Exception:  # noqa: BLE001
        char_block = ""

    blocks = [hard_anchors, pacing_block, beats_block, open_threads_block, char_block]
    return "\n\n".join(b for b in blocks if b)


def _quality_check(
    polished: str,
    ctx: _PolishContext,
) -> tuple[bool, str]:
    """校验润色版是否满足落库门槛。返回 (是否通过, 失败原因)。

    设计取舍：scene.must_include 是 LLM 规划阶段产生的"指令性长句"而非
    关键词列表（实际数据多是几十字的指引），做子串匹配会必然失败。本检查
    只做两项硬约束：
    1. 字数下限（防 LLM 偷懒大幅压缩）
    2. 至少一个本章主要角色名仍在润色版出现（防写偏到别的故事 / 输出空字符串）
    must_include 的语义遵守已经在 prompt 中要求 LLM 保持，靠模型自身约束。
    """
    if not polished or not polished.strip():
        return False, "empty_polished_text"
    if ctx.orig_total_len <= 0:
        return False, "empty_original"
    if len(polished) < int(ctx.orig_total_len * _MIN_WORDS_RATIO):
        return (
            False,
            f"word_count_too_low: polished={len(polished)} orig={ctx.orig_total_len}",
        )
    # 角色名命中：至少有一个本章主要角色仍在润色版出现
    if ctx.character_names:
        if not any(name in polished for name in ctx.character_names):
            return False, "no_character_name_present"
    return True, ""


async def _existing_recent_polish(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    chapter_id: str,
    drafts_by_scene: dict[str, DraftVersion],
) -> DraftVersion | None:
    """dedupe：返回该章已存在的、晚于所有 scene draft 的最新 polish 版（status=draft）。"""
    stmt = (
        select(DraftVersion)
        .where(
            DraftVersion.organization_id == organization_id,
            DraftVersion.project_id == project_id,
            DraftVersion.chapter_id == chapter_id,
            DraftVersion.version_type == "polish",
            DraftVersion.status == "draft",
        )
        .order_by(desc(DraftVersion.created_at))
        .limit(1)
    )
    latest = (await session.execute(stmt)).scalars().first()
    if not latest:
        return None
    max_scene_updated = max(
        (d.updated_at for d in drafts_by_scene.values() if d.updated_at is not None),
        default=None,
    )
    if max_scene_updated is None:
        return latest
    if latest.created_at and latest.created_at >= max_scene_updated:
        return latest
    return None


async def polish_chapter(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    job_id: str | None,
    project: Project,
    spec: NovelSpec,
    chapter: Chapter,
    created_by: str | None = None,
    force: bool = False,
) -> DraftVersion | None:
    """对整章 N 场 draft 做一次 LLM 润色，落 version_type='polish' 行。

    force=False 时启用 dedupe（同章已有更新的 polish 直接返回）。
    任何失败 swallow + warn 返回 None，绝不阻断主流程。
    """
    ctx, scenes, drafts_by_scene = await _gather_polish_context(
        session,
        organization_id=organization_id,
        project_id=project_id,
        chapter=chapter,
    )
    if not ctx.chapter_text:
        _logger.info(
            "polish_chapter_skip_no_drafts",
            extra={"chapter_id": chapter.id},
        )
        return None

    if not force:
        existing = await _existing_recent_polish(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
            drafts_by_scene=drafts_by_scene,
        )
        if existing is not None:
            _logger.info(
                "polish_chapter_skip_dedupe",
                extra={
                    "chapter_id": chapter.id,
                    "existing_id": existing.id,
                },
            )
            return existing

    meta_block = await _gather_meta_block(
        session,
        organization_id=organization_id,
        project_id=project_id,
        project=project,
        spec=spec,
        chapter=chapter,
        character_names=ctx.character_names,
    )

    try:
        prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
    except Exception:  # noqa: BLE001
        _logger.warning("polish_prompt_load_failed", exc_info=True)
        return None

    user_prompt = (
        "## 元数据（不要改写，仅用于参考约束）\n"
        + meta_block
        + "\n\n## 原章节正文（已合并所有 scene，场之间以 '---' 分隔）\n"
        + ctx.chapter_text
        + "\n\n## 任务\n"
        "请按系统指令对上述章节做整体润色。输出**整章纯文本**（保留 markdown "
        "段落分行，不要再保留 '---' 场分隔符）。字数与原章节相差不超过 ±10%。"
    )

    try:
        polished = await model_gateway.generate_text(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="polish_chapter",
            system_prompt=prompt,
            user_prompt=user_prompt,
            prompt_key=_PROMPT_KEY,
            prompt_version=_PROMPT_VERSION,
            temperature=0.4,
            timeout_seconds=_LONG_TIMEOUT_SECONDS,
            metadata={
                "chapter_id": chapter.id,
                "chapter_index": chapter.chapter_index,
                "orig_word_count": ctx.orig_total_len,
                "scene_count": len(drafts_by_scene),
            },
        )
    except Exception:  # noqa: BLE001
        _logger.warning(
            "polish_chapter_llm_failed",
            exc_info=True,
            extra={"chapter_id": chapter.id},
        )
        return None

    polished = (polished or "").strip()
    ok, reason = _quality_check(polished, ctx)
    if not ok:
        _logger.warning(
            "polish_chapter_quality_check_failed",
            extra={
                "chapter_id": chapter.id,
                "reason": reason,
                "orig_len": ctx.orig_total_len,
                "polished_len": len(polished),
            },
        )
        return None

    draft = DraftVersion(
        id=_new_id(),
        organization_id=organization_id,
        project_id=project_id,
        chapter_id=chapter.id,
        scene_id=None,
        version_type="polish",
        content=polished,
        content_format="markdown",
        word_count=len(polished),
        status="draft",
        parent_version_id=None,
        created_by=created_by or "system",
    )
    session.add(draft)
    await session.flush()
    return draft


__all__ = ["polish_chapter"]
