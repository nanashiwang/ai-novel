from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Sequence


@dataclass(frozen=True)
class SceneBeatGroup:
    scene_index: int
    beats: tuple[str, ...]
    beat_start: int | None = None
    beat_end: int | None = None

    @property
    def range_label(self) -> str:
        if self.beat_start is None or self.beat_end is None:
            return "补充承接/余波"
        if self.beat_start == self.beat_end:
            return f"beat {self.beat_start}"
        return f"beat {self.beat_start}-{self.beat_end}"


@dataclass(frozen=True)
class SceneBudgetAssignment:
    scene_index: int
    target_words: int
    beat_start: int | None
    beat_end: int | None
    beat_group_summary: str
    budget_reason: str


@dataclass(frozen=True)
class SceneBudgetPlan:
    scene_count: int
    scene_target_words: tuple[int, ...]
    beat_groups: tuple[SceneBeatGroup, ...]
    reason: str
    mode: str

    def target_for_scene(self, scene_index: int, default: int = 1200) -> int:
        if not self.scene_target_words:
            return default
        index = max(1, int(scene_index or 1)) - 1
        if index >= len(self.scene_target_words):
            index = len(self.scene_target_words) - 1
        return self.scene_target_words[index]

    def group_for_scene(self, scene_index: int) -> SceneBeatGroup | None:
        index = max(1, int(scene_index or 1)) - 1
        if index < len(self.beat_groups):
            return self.beat_groups[index]
        return self.beat_groups[-1] if self.beat_groups else None

    def assignment_for_scene(
        self,
        scene_index: int,
        default_words: int = 1200,
    ) -> SceneBudgetAssignment:
        group = self.group_for_scene(scene_index)
        target_words = self.target_for_scene(scene_index, default_words)
        beat_summary = ""
        beat_start = None
        beat_end = None
        if group:
            beat_start = group.beat_start
            beat_end = group.beat_end
            if group.beats:
                beat_summary = f"{group.range_label}：" + "；".join(group.beats)
            else:
                beat_summary = group.range_label
        return SceneBudgetAssignment(
            scene_index=max(1, int(scene_index or 1)),
            target_words=target_words,
            beat_start=beat_start,
            beat_end=beat_end,
            beat_group_summary=beat_summary,
            budget_reason=self.reason,
        )



_DENSE_PACING = {"climax", "finale", "battle", "reveal"}
_QUIET_PACING = {"transition", "cool_down"}


def build_scene_budget_plan(
    *,
    chapter: Any | None = None,
    target_words: int | None = None,
    scene_beats: Sequence[str] | None = None,
    pacing_type: str | None = None,
    emotion_intensity: int | None = None,
    requested_scene_count: int | None = None,
    forced_scene_count: int | None = None,
    fallback_scene_count: int = 3,
    fallback_scene_words: int = 1200,
) -> SceneBudgetPlan:
    """Decide scene count and word budget without treating beats as scenes.

    `requested_scene_count` is the user's manual override for generation.
    `forced_scene_count` is for already persisted scenes, where budget display must
    follow the actual current scene rows.
    """
    if chapter is not None:
        if target_words is None:
            target_words = getattr(chapter, "target_words", 0)
        if scene_beats is None:
            scene_beats = getattr(chapter, "scene_beats", [])
        if pacing_type is None:
            pacing_type = getattr(chapter, "pacing_type", "")
        emotion_intensity = (
            emotion_intensity
            if emotion_intensity is not None
            else getattr(chapter, "emotion_intensity", 3)
        )

    beats = tuple(str(item).strip() for item in (scene_beats or []) if str(item).strip())
    total_words = _as_positive_int(target_words)
    fallback_scene_count = _clamp_int(fallback_scene_count, 1, 8)
    fallback_scene_words = max(600, _as_positive_int(fallback_scene_words) or 1200)
    pacing = (pacing_type or "").strip().lower()
    emo = _clamp_int(emotion_intensity or 3, 1, 5)

    if forced_scene_count is not None:
        scene_count = max(1, int(forced_scene_count or 1))
        mode = "forced"
        reason = f"按当前已生成的 {scene_count} 个场景分配预算"
    elif requested_scene_count is not None:
        scene_count = _clamp_int(requested_scene_count, 1, 8)
        mode = "manual"
        reason = f"按手动指定的 {scene_count} 个场景"
    else:
        base_words = total_words or fallback_scene_words * fallback_scene_count
        scene_count = _auto_scene_count(
            base_words,
            pacing_type=pacing,
            emotion_intensity=emo,
        )
        mode = "auto"
        reason = (
            f"按章节目标字数 {base_words} 字、节奏 {pacing or '未标注'}、"
            f"情绪强度 {emo}/5 自动预算"
        )

    target_words_by_scene = _distribute_words(
        total_words=total_words,
        scene_count=scene_count,
        fallback_scene_words=fallback_scene_words,
    )
    beat_groups = _group_beats(beats, scene_count)
    return SceneBudgetPlan(
        scene_count=scene_count,
        scene_target_words=target_words_by_scene,
        beat_groups=beat_groups,
        reason=reason,
        mode=mode,
    )


def format_scene_budget_prompt_block(
    plan: SceneBudgetPlan,
    *,
    chapter_target_words: int = 0,
) -> str:
    lines = [
        "## 场景预算规则",
        (
            f"- 后端规则预算器已确定：本章必须拆成 {plan.scene_count} 个场景"
            f"（{plan.reason}）。"
        ),
        (
            "- scene_beats 是剧情拍点，不等同于场景数量；"
            "不要按 1 beat = 1 scene 机械拆分。"
        ),
        (
            f"- 最终 JSON 的 scenes 数量必须等于 {plan.scene_count}，"
            "scene_index 必须从 1 连续编号。"
        ),
    ]
    if chapter_target_words > 0:
        lines.append(
            f"- 本章总字数预算：约 {chapter_target_words} 字；"
            "每场按下方目标字数控制。"
        )
    lines.append("目标场景分组：")
    for group in plan.beat_groups:
        target_words = plan.target_for_scene(group.scene_index)
        if group.beats:
            beat_text = "；".join(group.beats)
            lines.append(
                f"- 场景 {group.scene_index}：覆盖 {group.range_label}，"
                f"目标约 {target_words} 字。{beat_text}"
            )
        else:
            lines.append(
                f"- 场景 {group.scene_index}：无固定 beat，负责承接、余波或过渡，"
                f"目标约 {target_words} 字。"
            )
    return "\n".join(lines) + "\n"


def _auto_scene_count(
    total_words: int,
    *,
    pacing_type: str,
    emotion_intensity: int,
) -> int:
    if total_words <= 1800:
        count = 1
    elif total_words <= 3600:
        count = 2
    elif total_words <= 5200:
        count = 3
    elif total_words <= 7000:
        count = 4
    else:
        count = _clamp_int(ceil(total_words / 1600), 4, 8)

    if (pacing_type in _DENSE_PACING or emotion_intensity >= 5) and count < 8:
        # 高潮章可以加场，但不能加到单场目标过短，避免制造 650 字问题。
        if total_words // (count + 1) >= 1000:
            count += 1
    elif pacing_type in _QUIET_PACING and count > 1:
        if total_words // (count - 1) <= 2600:
            count -= 1
    return _clamp_int(count, 1, 8)


def _group_beats(beats: Sequence[str], scene_count: int) -> tuple[SceneBeatGroup, ...]:
    groups: list[SceneBeatGroup] = []
    cursor = 0
    beat_count = len(beats)
    for scene_index in range(1, scene_count + 1):
        remaining_beats = beat_count - cursor
        remaining_slots = scene_count - scene_index + 1
        size = ceil(remaining_beats / remaining_slots) if remaining_beats > 0 else 0
        selected = tuple(beats[cursor : cursor + size])
        start = cursor + 1 if selected else None
        end = cursor + len(selected) if selected else None
        groups.append(
            SceneBeatGroup(
                scene_index=scene_index,
                beats=selected,
                beat_start=start,
                beat_end=end,
            )
        )
        cursor += size
    return tuple(groups)


def _distribute_words(
    *,
    total_words: int,
    scene_count: int,
    fallback_scene_words: int,
) -> tuple[int, ...]:
    if scene_count <= 0:
        return ()
    if total_words <= 0:
        return tuple(fallback_scene_words for _ in range(scene_count))
    base = total_words // scene_count
    remainder = total_words % scene_count
    return tuple(base + (1 if index < remainder else 0) for index in range(scene_count))


def _as_positive_int(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(number, high))
