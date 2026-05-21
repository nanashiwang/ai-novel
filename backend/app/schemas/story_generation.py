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
    goal: str = ""
    conflict: str = ""
    emotion_start: str = ""
    emotion_end: str = ""
    reveal: str = ""
    hook: str = ""
    expected_words: int = 1200

    @field_validator(
        "title",
        "time_marker",
        "location",
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
