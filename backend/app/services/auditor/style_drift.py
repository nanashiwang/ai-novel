"""风格漂移检测（Sprint 17-A 防漂移）。

每 100 章触发一次：抽取当前章节末尾对白样本，与前 100 章对白样本做
embedding cosine 相似度比较。距离过远则写入 continuity_issues
（issue_type='style_drift'），让作者/审稿人感知到风格已偏离。

实现要点：
- 仅取章末最后一个 scene 的最新 draft（代表性）
- 对白抽取：用正则匹配中文引号 "…" 内文本，回退到全文末尾片段
- embedding 失败 / 没有可比样本 → 静默跳过，不阻断主流程
- 相似度阈值 0.7 cosine（低于此判定为漂移）
"""
from __future__ import annotations

import logging
import math
import re
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.scene import Scene
from app.repositories import ContinuityIssueRepository
from app.services.embedding import embedding_service

_logger = logging.getLogger(__name__)

_DIALOGUE_RE = re.compile(r'[“"]([^“”"]{2,200})[”"]')
_DRIFT_THRESHOLD = 0.7  # cosine 低于此判定为漂移
_SAMPLE_CHARS = 2000
_DEFAULT_BASELINE_OFFSET = 100  # 与多少章前对比


def _extract_dialogue_sample(content: str, max_chars: int = _SAMPLE_CHARS) -> str:
    """从 draft 正文抽对白。返回拼接的对白片段（≤ max_chars）。

    优先：用引号正则。回退：返回末尾片段。
    """
    if not content:
        return ""
    matches = _DIALOGUE_RE.findall(content)
    if matches:
        joined = " ".join(matches)
        return joined[:max_chars]
    return content[-max_chars:]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    nb = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return dot / (na * nb)


async def _last_scene_draft_in_chapter(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    chapter_id: str,
) -> str | None:
    """取该章最末 scene 的最新 draft.content。"""
    stmt = (
        select(Scene)
        .where(
            Scene.organization_id == organization_id,
            Scene.project_id == project_id,
            Scene.chapter_id == chapter_id,
        )
        .order_by(desc(Scene.scene_index))
        .limit(1)
    )
    scene = (await session.execute(stmt)).scalars().first()
    if not scene:
        return None
    dstmt = (
        select(DraftVersion)
        .where(
            DraftVersion.organization_id == organization_id,
            DraftVersion.project_id == project_id,
            DraftVersion.scene_id == scene.id,
            DraftVersion.version_type == "draft",
        )
        .order_by(desc(DraftVersion.created_at))
        .limit(1)
    )
    draft = (await session.execute(dstmt)).scalars().first()
    return draft.content if draft else None


async def _baseline_dialogue_sample(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    current_chapter_index: int,
    offset: int,
) -> str | None:
    """取 current - offset 章的末场 draft 对白；不存在时取最近的更早章兜底。"""
    target_index = max(1, current_chapter_index - offset)
    cstmt = (
        select(Chapter)
        .where(
            Chapter.organization_id == organization_id,
            Chapter.project_id == project_id,
            Chapter.chapter_index <= target_index,
        )
        .order_by(desc(Chapter.chapter_index))
        .limit(1)
    )
    chap = (await session.execute(cstmt)).scalars().first()
    if not chap:
        return None
    content = await _last_scene_draft_in_chapter(
        session,
        organization_id=organization_id,
        project_id=project_id,
        chapter_id=chap.id,
    )
    if not content:
        return None
    return _extract_dialogue_sample(content)


async def check_style_drift(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    chapter_id: str,
    current_chapter_index: int,
    baseline_offset: int = _DEFAULT_BASELINE_OFFSET,
    threshold: float = _DRIFT_THRESHOLD,
) -> dict | None:
    """对当前章末场对白 vs baseline_offset 章前对白做 embedding 相似度检测。

    返回 dict 包含 cosine / drifted；若 drifted=True 也已写入 continuity_issues。
    任何无法比较的情况返回 None。
    """
    if current_chapter_index <= baseline_offset:
        return None
    current_content = await _last_scene_draft_in_chapter(
        session,
        organization_id=organization_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    if not current_content:
        return None
    current_dialogue = _extract_dialogue_sample(current_content)
    if not current_dialogue:
        return None
    baseline_dialogue = await _baseline_dialogue_sample(
        session,
        organization_id=organization_id,
        project_id=project_id,
        current_chapter_index=current_chapter_index,
        offset=baseline_offset,
    )
    if not baseline_dialogue:
        return None
    try:
        cur_vec = await embedding_service.embed(current_dialogue)
        base_vec = await embedding_service.embed(baseline_dialogue)
    except Exception:  # noqa: BLE001
        _logger.warning("style_drift_embed_failed", exc_info=True)
        return None
    if not cur_vec or not base_vec:
        return None
    cosine = _cosine(cur_vec, base_vec)
    drifted = cosine < threshold
    if drifted:
        try:
            await ContinuityIssueRepository(session).create(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter_id,
                scene_id=None,
                issue_type="style_drift",
                severity="medium",
                description=(
                    f"对白风格已偏离 {baseline_offset} 章前基线（cosine={cosine:.3f} <"
                    f" 阈值 {threshold}）。建议回看早期章节对白节奏与措辞。"
                ),
                suggested_fix=(
                    "在接下来 3-5 章中保持人物口吻、句式长度、用词层级与早期一致；"
                    "或显式承认风格演化是有意为之并更新风格守则。"
                ),
                status="open",
            )
        except Exception:  # noqa: BLE001
            _logger.warning("style_drift_issue_write_failed", exc_info=True)
    return {"cosine": cosine, "drifted": drifted, "threshold": threshold}


__all__ = ["check_style_drift", "_extract_dialogue_sample"]
