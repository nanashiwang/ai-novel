from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.schemas.common import APIModel

StateEntityType = Literal["character", "artifact", "plot_thread", "relationship", "world_rule"]
StateType = Literal["skill", "artifact", "identity", "grudge", "foreshadow", "oath"]
StateStatus = Literal["active", "hidden", "damaged", "resolved", "consumed", "inactive"]
StateChangeType = Literal[
    "create",
    "update",
    "resolve",
    "remove",
    "reveal",
    "hide",
    "upgrade",
    "damage",
    "repair",
]
RequirementType = Literal[
    "must_remember",
    "must_not_conflict",
    "should_reference",
    "candidate_payoff",
]
RequirementOriginType = Literal[
    "current_chapter_extract",
    "previous_chapter_carryover",
    "manual",
    "backfill",
]
RequirementStatus = Literal["active", "superseded", "resolved", "disabled"]


class StoryStateItemResponse(APIModel):
    id: str
    entity_type: StateEntityType
    entity_id: str | None = None
    state_type: StateType
    name: str
    status: StateStatus
    summary: str
    value_json: dict[str, Any] = Field(default_factory=dict)
    source_chapter_id: str | None = None
    source_scene_id: str | None = None
    source_excerpt: str = ""
    updated_in_chapter_id: str | None = None
    priority: int
    is_hard_constraint: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StoryStateListResponse(APIModel):
    items: list[StoryStateItemResponse] = Field(default_factory=list)


class StoryStateHistoryResponse(APIModel):
    id: str
    state_item_id: str
    chapter_id: str | None = None
    scene_id: str | None = None
    change_type: StateChangeType
    before_json: dict[str, Any] = Field(default_factory=dict)
    after_json: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    source_excerpt: str = ""
    created_by: str | None = None
    created_at: datetime | None = None


class StoryStateHistoryListResponse(APIModel):
    items: list[StoryStateHistoryResponse] = Field(default_factory=list)


class ChapterStateRequirementResponse(APIModel):
    id: str
    state_item_id: str
    requirement_type: RequirementType
    summary: str = ""
    priority: int
    origin_type: RequirementOriginType = "current_chapter_extract"
    status: RequirementStatus = "active"
    superseded_by_requirement_id: str | None = None
    source_issue_id: str | None = None
    status_reason: str = ""
    source_chapter_id: str | None = None
    source_chapter_index: int | None = None
    source_chapter_title: str | None = None
    source_scene_id: str | None = None
    target_chapter_id: str | None = None
    state_item: StoryStateItemResponse | None = None


class ChapterStateRequirementListResponse(APIModel):
    items: list[ChapterStateRequirementResponse] = Field(default_factory=list)


class AntiForgettingPreviewResponse(APIModel):
    project_id: str
    chapter_id: str
    scene_id: str
    purpose: Literal["writing", "audit"] = "writing"
    prompt_block: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    requirements: list[ChapterStateRequirementResponse] = Field(default_factory=list)
    story_states: list[StoryStateItemResponse] = Field(default_factory=list)


class ChapterStateRequirementCreateRequest(APIModel):
    state_item_id: str
    requirement_type: RequirementType = "must_remember"
    summary: str = ""
    priority: int = Field(default=80, ge=0)
    source_issue_id: str | None = None


class ChapterStateRequirementPatchRequest(APIModel):
    requirement_type: RequirementType | None = None
    summary: str | None = None
    priority: int | None = Field(default=None, ge=0)
    status: RequirementStatus | None = None
    superseded_by_requirement_id: str | None = None
    status_reason: str | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> ChapterStateRequirementPatchRequest:
        if all(
            value is None
            for value in (
                self.requirement_type,
                self.summary,
                self.priority,
                self.status,
                self.superseded_by_requirement_id,
                self.status_reason,
            )
        ):
            raise ValueError("At least one updatable field is required")
        return self


class StoryStatePatchRequest(APIModel):
    status: StateStatus | None = None
    summary: str | None = None
    value_json: dict[str, Any] | None = None
    priority: int | None = None
    is_hard_constraint: bool | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> StoryStatePatchRequest:
        if all(
            value is None
            for value in (
                self.status,
                self.summary,
                self.value_json,
                self.priority,
                self.is_hard_constraint,
            )
        ):
            raise ValueError("At least one updatable field is required")
        return self
