from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from .common import APIModel


class CharacterSeed(APIModel):
    name: str = ""
    role: str = ""
    description: str = ""
    personality: str = ""
    motivation: str = ""
    secret: str = ""
    arc: str = ""
    relationships: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "name",
        "role",
        "description",
        "personality",
        "motivation",
        "secret",
        "arc",
        mode="before",
    )
    @classmethod
    def stringify_text(cls, value: Any) -> str:
        if isinstance(value, list):
            return "；".join(str(item) for item in value)
        if isinstance(value, dict):
            return "；".join(f"{key}: {item}" for key, item in value.items())
        return "" if value is None else str(value)

    @field_validator("relationships", "current_state", mode="before")
    @classmethod
    def normalize_mapping(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}


class LorebookSeed(APIModel):
    name: str = ""
    description: str = ""
    importance: str = "medium"

    @model_validator(mode="before")
    @classmethod
    def normalize_text_seed(cls, data: Any) -> Any:
        if isinstance(data, str):
            text = data.strip()
            return {"name": text[:80], "description": text}
        if isinstance(data, dict):
            name = data.get("name") or data.get("title") or data.get("label") or ""
            description = (
                data.get("description") or data.get("summary") or data.get("content") or name
            )
            return {
                **data,
                "name": str(name).strip(),
                "description": str(description).strip(),
            }
        return data


class StoryBibleContract(APIModel):
    premise: str = ""
    theme: str = ""
    genre: str = ""
    tone: str = ""
    target_reader: str = ""
    narrative_pov: str = ""
    style_guide: str = ""
    constraints: list[str] = Field(default_factory=list)
    locations: list[LorebookSeed] = Field(default_factory=list)
    factions: list[LorebookSeed] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    main_characters: list[CharacterSeed] = Field(default_factory=list)
    continuity_rules: list[str] = Field(default_factory=list)
    plot_threads: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_lorebook_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "locations" not in data:
            for key in ("world_locations", "key_locations", "places"):
                if key in data:
                    data = {**data, "locations": data[key]}
                    break
        if "factions" not in data:
            for key in ("organizations", "forces", "power_groups", "key_organizations"):
                if key in data:
                    data = {**data, "factions": data[key]}
                    break
        return data


class ChapterPlanItem(APIModel):
    chapter_index: int = 0
    # 跟 ScenePlanItem 同样的鲁棒性考虑：LLM 漏字段时不让整次大纲生成 fail，
    # normalize 阶段会补默认标题
    title: str = ""
    summary: str = ""
    goal: str = ""
    conflict: str = ""
    ending_hook: str = ""
    volume_index: int | None = None
    # Sprint 16-E1：字数预算与场景拍点。
    # target_words 为 0 时 activity 会按 spec.target_word_count /
    # target_chapter_count 反推默认值；scene_beats 为空时回落到调用方
    # 显式指定的 scenes_per_chapter。
    target_words: int = 0
    scene_beats: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and "chapter_index" not in data and "chapter" in data:
            data = {**data, "chapter_index": data.get("chapter")}
        return data

    @field_validator("summary", "goal", "conflict", "ending_hook", mode="before")
    @classmethod
    def stringify_text(cls, value: Any) -> str:
        if isinstance(value, list):
            return "；".join(str(item) for item in value)
        if isinstance(value, dict):
            return "；".join(f"{key}: {item}" for key, item in value.items())
        return "" if value is None else str(value)

    @field_validator("scene_beats", mode="before")
    @classmethod
    def normalize_scene_beats(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        # LLM 偶尔会输出 string，按行 / 中文分号拆分
        if isinstance(value, str):
            for sep in ("\n", "；", ";"):
                if sep in value:
                    return [s.strip() for s in value.split(sep) if s.strip()]
            return [value.strip()] if value.strip() else []
        return [str(value)]


class ChapterPlanContract(APIModel):
    chapters: list[ChapterPlanItem] = Field(default_factory=list)


class ScenePlanItem(APIModel):
    scene_index: int
    # LLM 偶尔会漏掉 title 字段（即使 prompt 指定了 schema），把它从 required
    # 改成可选；normalize_scenes 会在 title 为空时按 chapter+scene_index 自动
    # 补一个默认标题，避免整次场景计划生成 fail。
    title: str = ""
    time_marker: str = ""
    location: str = ""
    characters: list[str] = Field(default_factory=list)
    scene_purpose: str = ""
    entry_state: str = ""
    exit_state: str = ""
    goal: str = ""
    conflict: str = ""
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    emotion_start: str = ""
    emotion_end: str = ""
    reveal: str = ""
    hook: str = ""
    expected_words: int = 1200
    # Sprint 14-C6：LLM 输出场景计划时可指定 POV 主角名（应在 characters 内）
    pov_character_name: str | None = None

    @field_validator(
        "title",
        "time_marker",
        "location",
        "scene_purpose",
        "entry_state",
        "exit_state",
        "goal",
        "conflict",
        "emotion_start",
        "emotion_end",
        "reveal",
        "hook",
        mode="before",
    )
    @classmethod
    def stringify_text(cls, value: Any) -> str:
        if isinstance(value, list):
            return "；".join(str(item) for item in value)
        if isinstance(value, dict):
            return "；".join(f"{key}: {item}" for key, item in value.items())
        return "" if value is None else str(value)

    @field_validator("pov_character_name", mode="before")
    @classmethod
    def normalize_pov(cls, value: Any) -> str | None:
        """空字符串 / None / 空白都视作"未指定 POV"——保持 None 语义。"""
        if value is None:
            return None
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, dict):
            value = value.get("name") or value.get("character") or None
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("characters", "must_include", "must_avoid", mode="before")
    @classmethod
    def normalize_text_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        names: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("role")
                if name:
                    names.append(str(name))
            elif item is not None:
                names.append(str(item))
        return names


class ScenePlanContract(APIModel):
    chapter_index: int = 0
    chapter_title: str = ""
    scenes: list[ScenePlanItem] = Field(default_factory=list)


class SceneDraftContract(APIModel):
    scene_id: str
    title: str = ""
    content: str = ""
    word_count: int = 0
    continuity_notes: list[str] = Field(default_factory=list)
    unresolved_threads: list[str] = Field(default_factory=list)


class CharacterStateUpdateItem(APIModel):
    name: str = ""
    current_state: dict[str, Any] = Field(default_factory=dict)
    relationships: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""

    @field_validator("name", "summary", mode="before")
    @classmethod
    def stringify_text(cls, value: Any) -> str:
        if isinstance(value, list):
            return "；".join(str(item) for item in value)
        if isinstance(value, dict):
            return "；".join(f"{key}: {item}" for key, item in value.items())
        return "" if value is None else str(value)

    @field_validator("current_state", "relationships", mode="before")
    @classmethod
    def normalize_mapping(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}


class CharacterStateUpdateContract(APIModel):
    updates: list[CharacterStateUpdateItem] = Field(default_factory=list)


class AuditIssueItem(APIModel):
    """单条 continuity / character / world / style 审稿问题。

    issue_type 与后端 ContinuityIssue.issue_type 字段对齐；severity 用
    low/medium/high 三档，UI 直接按 severity 着色。
    """

    issue_type: str = "continuity"
    severity: str = "medium"
    description: str = ""
    suggested_fix: str = ""

    @field_validator("issue_type", mode="before")
    @classmethod
    def normalize_issue_type(cls, value: Any) -> str:
        v = ("" if value is None else str(value)).lower().strip()
        # 把模型偶尔吐出的中文/同义词映射到固定枚举
        mapping = {
            "连续性": "continuity",
            "continuity": "continuity",
            "人物": "character",
            "character": "character",
            "世界": "world_rule",
            "world": "world_rule",
            "world_rule": "world_rule",
            "风格": "style",
            "style": "style",
        }
        return mapping.get(v, v or "continuity")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> str:
        v = ("" if value is None else str(value)).lower().strip()
        mapping = {
            "高": "high",
            "中": "medium",
            "低": "low",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }
        return mapping.get(v, v or "medium")


class AuditResultContract(APIModel):
    issues: list[AuditIssueItem] = Field(default_factory=list)


class BeatItem(APIModel):
    """单个 beat（情节段落点）。

    Sprint 14-C3 多 agent 场景写作：planner 把一个 scene 拆成 4~8 个 beat，
    drafter 再按每个 beat 写正文。各字段语义：
    - index: 在 scene 内的顺序，从 1 开始
    - purpose: 该段在叙事节奏中的目的（开场/推进/转折/结尾/钩子等）
    - action: 角色具体做了什么（show 优先，避免抽象总结）
    - dialog_hint: 对白要点，可空（不强制每段都写对白）
    - reaction: 角色的反应/内心变化，让节奏更紧
    - target_words: 该 beat 的目标字数，所有 beat 之和约等于 scene 目标字数
    """

    index: int
    purpose: str
    action: str
    dialog_hint: str = ""
    reaction: str = ""
    target_words: int

    @field_validator(
        "purpose",
        "action",
        "dialog_hint",
        "reaction",
        mode="before",
    )
    @classmethod
    def stringify_text(cls, value: Any) -> str:
        if isinstance(value, list):
            return "；".join(str(item) for item in value)
        if isinstance(value, dict):
            return "；".join(f"{key}: {item}" for key, item in value.items())
        return "" if value is None else str(value)

    @field_validator("target_words", mode="before")
    @classmethod
    def normalize_target_words(cls, value: Any) -> int:
        # 模型偶尔会输出字符串数字或 None；统一兜底成正整数。
        try:
            v = int(value)
        except (TypeError, ValueError):
            return 200
        return max(50, v)


class BeatSheetContract(APIModel):
    """planner 阶段产出：一个 scene 的全部 beat 列表。"""

    beats: list[BeatItem] = Field(default_factory=list)
    total_target_words: int = 0

    @field_validator("total_target_words", mode="before")
    @classmethod
    def normalize_total(cls, value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
