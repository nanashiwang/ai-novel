"""AI 关键设定维护器。

正文生成/重写后，基于最新 draft 自动判断哪些长期设定需要轻量维护。
低风险高置信自动应用；中风险高置信且支持撤销的动作也可自动应用。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.chapter import Chapter
from app.models.chapter_state_requirement import ChapterStateRequirement
from app.models.continuity_issue import ContinuityIssue
from app.models.draft_version import DraftVersion
from app.models.scene import Scene
from app.models.story_state_item import StoryStateItem
from app.models.story_state_maintenance_action import StoryStateMaintenanceAction
from app.repositories import (
    ChapterStateRequirementRepository,
    StoryStateHistoryRepository,
    StoryStateMaintenanceActionRepository,
    StoryStateRepository,
)
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager
from app.services.story_state.service import story_state_service

_logger = logging.getLogger(__name__)

_PROMPT_KEY = "story_state/maintain_after_draft"
_PROMPT_VERSION = "v1"

_ALLOWED_ACTION_TYPES = {
    "create_state",
    "update_state",
    "merge_states",
    "supersede_state",
    "create_requirement",
    "resolve_requirement",
    "supersede_requirement",
}
_ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
_ALLOWED_ENTITY_TYPES = {"character", "artifact", "plot_thread", "relationship", "world_rule"}
_ALLOWED_STATE_TYPES = {"skill", "artifact", "identity", "grudge", "foreshadow", "oath"}
_ALLOWED_REQUIREMENT_TYPES = {
    "must_remember",
    "must_not_conflict",
    "should_reference",
    "candidate_payoff",
}
_AUTO_APPLY_CONFIDENCE = 0.85
_MEDIUM_AUTO_APPLY_CONFIDENCE = 0.88
_SUGGEST_ONLY_CONFIDENCE = 0.75
_MAX_ACTIONS_PER_RUN = 20
_FUTURE_REQUIREMENT_DEFAULT_CHAPTER_COUNT = 3
_FUTURE_REQUIREMENT_MAX_CHAPTER_COUNT = 8
_FUTURE_REQUIREMENT_REASON_PREFIX = "ai_maintenance_action:"
_FUTURE_REQUIREMENT_ACTION_TYPES = {"create_state", "update_state", "supersede_state"}
_ALLOWED_STATE_STATUSES = {"active", "hidden", "damaged", "resolved", "consumed"}
_ROLLBACK_UNSUPPORTED_ACTIONS = {"merge_states"}
_STATE_RESTORE_FIELDS = {
    "entity_type",
    "entity_id",
    "state_type",
    "name",
    "status",
    "superseded_by_state_id",
    "status_reason",
    "summary",
    "value_json",
    "source_chapter_id",
    "source_scene_id",
    "source_excerpt",
    "updated_in_chapter_id",
    "priority",
    "is_hard_constraint",
}
_REQUIREMENT_RESTORE_FIELDS = {
    "chapter_id",
    "source_chapter_id",
    "source_scene_id",
    "target_chapter_id",
    "origin_type",
    "status",
    "superseded_by_requirement_id",
    "source_issue_id",
    "status_reason",
    "state_item_id",
    "requirement_type",
    "summary",
    "priority",
}


@dataclass(slots=True)
class _ParsedAction:
    action_type: str
    target_state_id: str | None = None
    source_state_ids: list[str] = field(default_factory=list)
    target_requirement_id: str | None = None
    superseded_by_requirement_id: str | None = None
    risk_level: str = "low"
    confidence: float = 0.0
    reason: str = ""
    patch: dict[str, Any] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_id(value: Any) -> str | None:
    text = _clean_text(value)
    return text or None


def _json_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _float_between_zero_and_one(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dedupe_ids(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item_id = _clean_id(value)
        if item_id and item_id not in seen:
            result.append(item_id)
            seen.add(item_id)
    return result


def _state_snapshot(state: StoryStateItem) -> dict[str, Any]:
    snapshot = story_state_service.snapshot(state)
    snapshot["id"] = state.id
    return snapshot


def _requirement_snapshot(row: ChapterStateRequirement) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "chapter_id": row.chapter_id,
        "source_chapter_id": row.source_chapter_id,
        "source_scene_id": row.source_scene_id,
        "target_chapter_id": row.target_chapter_id,
        "origin_type": row.origin_type,
        "status": row.status or "active",
        "superseded_by_requirement_id": row.superseded_by_requirement_id,
        "source_issue_id": row.source_issue_id,
        "status_reason": row.status_reason or "",
        "state_item_id": row.state_item_id,
        "requirement_type": row.requirement_type,
        "summary": row.summary,
        "priority": row.priority,
    }


def _issue_payload(row: ContinuityIssue) -> dict[str, Any]:
    return {
        "id": row.id,
        "chapter_id": row.chapter_id,
        "scene_id": row.scene_id,
        "story_state_item_id": row.story_state_item_id,
        "issue_type": row.issue_type,
        "severity": row.severity,
        "description": row.description,
        "suggested_fix": row.suggested_fix,
        "status": row.status,
    }


def _normalize_snapshot_value(field: str, value: Any) -> Any:
    if field == "value_json":
        return dict(value or {}) if isinstance(value, dict) else {}
    if field == "priority":
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    if field == "is_hard_constraint":
        return bool(value)
    if field in {"status_reason", "summary", "source_excerpt"}:
        return _clean_text(value)
    return value


def _snapshot_matches_model(row: Any, snapshot: dict[str, Any], fields: set[str]) -> bool:
    for field in fields:
        if field not in snapshot:
            continue
        expected = _normalize_snapshot_value(field, snapshot.get(field))
        current = _normalize_snapshot_value(field, getattr(row, field, None))
        if current != expected:
            return False
    return True


def _restore_model_snapshot(row: Any, snapshot: dict[str, Any], fields: set[str]) -> None:
    for field in fields:
        if field not in snapshot:
            continue
        setattr(row, field, _normalize_snapshot_value(field, snapshot.get(field)))


def _is_rollback_supported(action: _ParsedAction) -> bool:
    return action.action_type not in _ROLLBACK_UNSUPPORTED_ACTIONS


def _policy_decision_for_action(action: _ParsedAction) -> dict[str, Any]:
    rollback_supported = _is_rollback_supported(action)
    if action.risk_level == "high":
        return {
            "status": "needs_review",
            "policy": "high_risk_needs_review",
            "auto_applied": False,
            "rollback_supported": rollback_supported,
            "threshold": None,
            "reason": "高风险动作必须人工确认",
        }
    if action.confidence < _SUGGEST_ONLY_CONFIDENCE:
        return {
            "status": "suggested",
            "policy": "low_confidence_suggested",
            "auto_applied": False,
            "rollback_supported": rollback_supported,
            "threshold": _SUGGEST_ONLY_CONFIDENCE,
            "reason": "置信度低于建议阈值，仅记录建议",
        }
    if action.risk_level == "medium":
        if rollback_supported and action.confidence >= _MEDIUM_AUTO_APPLY_CONFIDENCE:
            return {
                "status": "applied",
                "policy": "medium_confident_rollbackable",
                "auto_applied": True,
                "rollback_supported": True,
                "threshold": _MEDIUM_AUTO_APPLY_CONFIDENCE,
                "reason": "中风险高置信且支持撤销，自动应用并保留撤销兜底",
            }
        return {
            "status": "needs_review",
            "policy": (
                "medium_rollback_unsupported"
                if not rollback_supported
                else "medium_confidence_below_auto_apply"
            ),
            "auto_applied": False,
            "rollback_supported": rollback_supported,
            "threshold": _MEDIUM_AUTO_APPLY_CONFIDENCE,
            "reason": (
                "该中风险动作暂不支持撤销，需人工确认"
                if not rollback_supported
                else "中风险动作置信度未达到自动应用阈值，需人工确认"
            ),
        }
    if action.confidence >= _AUTO_APPLY_CONFIDENCE:
        return {
            "status": "applied",
            "policy": "low_confident_auto_apply",
            "auto_applied": True,
            "rollback_supported": rollback_supported,
            "threshold": _AUTO_APPLY_CONFIDENCE,
            "reason": "低风险高置信，自动应用",
        }
    return {
        "status": "suggested",
        "policy": "low_confidence_below_auto_apply",
        "auto_applied": False,
        "rollback_supported": rollback_supported,
        "threshold": _AUTO_APPLY_CONFIDENCE,
        "reason": "低风险动作置信度未达到自动应用阈值，仅记录建议",
    }


def _patch_json_for_action(
    action: _ParsedAction,
    *,
    auto_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patch = dict(action.patch or {})
    if action.superseded_by_requirement_id:
        patch["superseded_by_requirement_id"] = action.superseded_by_requirement_id
    if auto_decision:
        patch["auto_decision"] = auto_decision
    return patch


def _clean_requirement_type(value: Any) -> str:
    requirement_type = _clean_text(value)
    return requirement_type if requirement_type in _ALLOWED_REQUIREMENT_TYPES else "must_remember"


def _clean_entity_type(value: Any) -> str:
    entity_type = _clean_text(value)
    return entity_type if entity_type in _ALLOWED_ENTITY_TYPES else ""


def _clean_state_type(value: Any) -> str:
    state_type = _clean_text(value)
    return state_type if state_type in _ALLOWED_STATE_TYPES else ""


def _compact_match_text(value: Any) -> str:
    return "".join(
        char.lower()
        for char in _clean_text(value)
        if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    )


def _bounded_future_chapter_count(value: Any, *, default: int | None = None) -> int:
    count = _safe_int(value, default or _FUTURE_REQUIREMENT_DEFAULT_CHAPTER_COUNT)
    return max(1, min(_FUTURE_REQUIREMENT_MAX_CHAPTER_COUNT, count))


def _priority_from_issue(issue: ContinuityIssue | None) -> int:
    severity = _clean_text(issue.severity if issue else "").lower()
    if severity == "high":
        return 96
    if severity == "medium":
        return 88
    if severity == "low":
        return 80
    return 85


def _action_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": sorted(_ALLOWED_ACTION_TYPES)},
                        "target_state_id": {"type": ["string", "null"]},
                        "source_state_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "target_requirement_id": {"type": ["string", "null"]},
                        "superseded_by_requirement_id": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "risk_level": {
                            "type": "string",
                            "enum": sorted(_ALLOWED_RISK_LEVELS),
                        },
                        "reason": {"type": "string"},
                        "patch": {"type": "object"},
                    },
                    "required": ["type", "confidence", "risk_level", "reason"],
                },
            }
        },
        "required": ["actions"],
    }


def _parse_action(entry: Any) -> _ParsedAction | None:
    if not isinstance(entry, dict):
        return None
    action_type = _clean_text(entry.get("type") or entry.get("action_type"))
    if action_type not in _ALLOWED_ACTION_TYPES:
        return None
    source_state_ids = entry.get("source_state_ids")
    if isinstance(source_state_ids, str):
        source_ids = _dedupe_ids([source_state_ids])
    else:
        source_ids = _dedupe_ids(_json_list(source_state_ids))
    risk_level = _clean_text(entry.get("risk_level")).lower()
    if risk_level not in _ALLOWED_RISK_LEVELS:
        risk_level = "high"
    return _ParsedAction(
        action_type=action_type,
        target_state_id=_clean_id(entry.get("target_state_id") or entry.get("state_id")),
        source_state_ids=source_ids,
        target_requirement_id=_clean_id(
            entry.get("target_requirement_id") or entry.get("requirement_id")
        ),
        superseded_by_requirement_id=_clean_id(
            entry.get("superseded_by_requirement_id")
            or entry.get("replacement_requirement_id")
        ),
        risk_level=risk_level,
        confidence=_float_between_zero_and_one(entry.get("confidence")),
        reason=_clean_text(entry.get("reason")),
        patch=_json_dict(entry.get("patch")),
    )


def _status_for_policy(action: _ParsedAction) -> str:
    return str(_policy_decision_for_action(action)["status"])


def _merge_value_json(
    target_value: dict[str, Any],
    source_states: list[StoryStateItem],
    patch_value: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(target_value or {})
    for source in source_states:
        for key, value in dict(source.value_json or {}).items():
            merged.setdefault(key, value)
    if patch_value:
        merged.update(dict(patch_value))
    return merged


class StoryStateMaintainerService:
    async def rollback_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action_id: str,
        created_by: str | None,
    ) -> StoryStateMaintenanceAction:
        """撤销一条已自动应用的维护动作。"""
        action = await StoryStateMaintenanceActionRepository(session).get(
            action_id,
            organization_id=organization_id,
        )
        if not action or action.project_id != project_id:
            raise NotFoundError("story_state_maintenance_action_not_found")
        if action.status != "applied":
            raise ConflictError("story_state_maintenance_action_not_applied")
        if action.action_type in _ROLLBACK_UNSUPPORTED_ACTIONS:
            raise ConflictError("story_state_maintenance_action_rollback_unsupported")

        if action.action_type == "create_state":
            await self._rollback_create_state_action(
                session,
                organization_id=organization_id,
                project_id=project_id,
                action=action,
                created_by=created_by,
            )
        elif action.action_type == "update_state":
            await self._rollback_update_state_action(
                session,
                organization_id=organization_id,
                project_id=project_id,
                action=action,
                created_by=created_by,
            )
        elif action.action_type == "create_requirement":
            await self._rollback_create_requirement_action(
                session,
                organization_id=organization_id,
                project_id=project_id,
                action=action,
                created_by=created_by,
            )
        elif action.action_type == "supersede_state":
            await self._rollback_supersede_state_action(
                session,
                organization_id=organization_id,
                project_id=project_id,
                action=action,
                created_by=created_by,
            )
        elif action.action_type in {"resolve_requirement", "supersede_requirement"}:
            await self._rollback_requirement_action(
                session,
                organization_id=organization_id,
                project_id=project_id,
                action=action,
                created_by=created_by,
            )
        else:
            raise ConflictError("story_state_maintenance_action_rollback_unsupported")

        await self._rollback_future_requirements_for_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=action,
            created_by=created_by,
        )
        action.status = "rolled_back"
        await session.flush()
        return action

    async def apply_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action_id: str,
        created_by: str | None,
    ) -> StoryStateMaintenanceAction:
        """人工确认并应用一条 AI 建议/待确认动作。"""
        action = await StoryStateMaintenanceActionRepository(session).get(
            action_id,
            organization_id=organization_id,
        )
        if not action or action.project_id != project_id:
            raise NotFoundError("story_state_maintenance_action_not_found")
        if action.status == "applied":
            return action
        if action.status not in {"suggested", "needs_review"}:
            raise ConflictError("story_state_maintenance_action_not_applicable")

        parsed = self._parsed_action_from_row(action)
        chapter = await self._load_action_chapter(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=action.chapter_id,
        )
        scene = await self._load_action_scene(
            session,
            organization_id=organization_id,
            project_id=project_id,
            scene_id=action.scene_id,
        )

        try:
            after_json: dict[str, Any]
            if parsed.action_type == "create_state":
                after_json = await self._apply_logged_create_state_action(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter=chapter,
                    scene=scene,
                    action_row=action,
                    parsed=parsed,
                    created_by=created_by,
                )
            elif parsed.action_type == "update_state":
                after_json = await self._apply_logged_update_state_action(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter=chapter,
                    scene=scene,
                    action_row=action,
                    parsed=parsed,
                    created_by=created_by,
                )
            elif parsed.action_type == "merge_states":
                after_json = await self._apply_logged_merge_states_action(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter=chapter,
                    scene=scene,
                    action_row=action,
                    parsed=parsed,
                    created_by=created_by,
                )
            elif parsed.action_type == "supersede_state":
                after_json = await self._apply_logged_supersede_state_action(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter=chapter,
                    scene=scene,
                    action_row=action,
                    parsed=parsed,
                    created_by=created_by,
                )
            elif parsed.action_type == "create_requirement":
                after_json = await self._apply_logged_create_requirement_action(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter=chapter,
                    scene=scene,
                    action_row=action,
                    parsed=parsed,
                    created_by=created_by,
                )
            elif parsed.action_type in {"resolve_requirement", "supersede_requirement"}:
                after_json = await self._apply_logged_requirement_action(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    chapter=chapter,
                    scene=scene,
                    action_row=action,
                    parsed=parsed,
                    created_by=created_by,
                )
            else:
                raise ConflictError("story_state_maintenance_action_apply_unsupported")
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

        action.status = "applied"
        action.applied_at = _now()
        action.after_json = after_json
        await session.flush()
        future_result = await self._apply_future_requirements_for_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            action_row=action,
            parsed=parsed,
            created_by=created_by,
        )
        if future_result:
            action.after_json = {**dict(action.after_json or {}), **future_result}
        await session.flush()
        return action

    async def maintain_after_draft(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str | None,
        chapter: Chapter,
        scene: Scene,
        draft: DraftVersion,
        created_by: str | None,
        source: str = "draft",
    ) -> dict[str, Any]:
        """正文落库后维护关键设定；失败返回 error，不抛出给写作主流程。"""
        if not draft or not (draft.content or "").strip():
            return {
                "suggested_count": 0,
                "applied_count": 0,
                "needs_review_count": 0,
                "skipped_count": 0,
                "skipped": "no_draft",
            }

        states = await self._load_story_states(
            session,
            organization_id=organization_id,
            project_id=project_id,
        )
        requirements = list(
            await ChapterStateRequirementRepository(session).list_for_chapter(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter.id,
                status="active",
            )
        )
        issues = await self._load_open_issues(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
        )
        if source == "audit_scene" and not states and not requirements and not issues:
            return {
                "suggested_count": 0,
                "applied_count": 0,
                "needs_review_count": 0,
                "skipped_count": 0,
                "skipped": "no_context",
            }

        try:
            prompt = prompt_manager.load(_PROMPT_KEY, version=_PROMPT_VERSION)
            raw = await model_gateway.generate_json(
                session,
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                task_type="maintain_story_state",
                system_prompt=prompt
                or "你是小说关键设定数据库维护器，只输出 JSON 动作。",
                user_prompt=json.dumps(
                    self._prompt_payload(
                        chapter=chapter,
                        scene=scene,
                        draft=draft,
                        states=states,
                        requirements=requirements,
                        issues=issues,
                        source=source,
                    ),
                    ensure_ascii=False,
                ),
                schema=_action_schema(),
                prompt_key=_PROMPT_KEY,
                prompt_version=_PROMPT_VERSION,
                temperature=0.1,
                metadata={
                    "scene_id": scene.id,
                    "chapter_id": chapter.id,
                    "maintenance_source": source,
                    "continuity_issue_count": len(issues),
                },
            )
        except Exception:  # noqa: BLE001
            _logger.warning(
                "story_state_maintenance_model_failed",
                exc_info=True,
                extra={"scene_id": scene.id, "chapter_id": chapter.id},
            )
            return {
                "suggested_count": 0,
                "applied_count": 0,
                "needs_review_count": 0,
                "skipped_count": 1,
                "error": "model_failed",
            }

        actions = (raw or {}).get("actions") if isinstance(raw, dict) else None
        if not isinstance(actions, list):
            return {
                "suggested_count": 0,
                "applied_count": 0,
                "needs_review_count": 0,
                "skipped_count": 1,
                "error": "invalid_response",
            }

        counts = {
            "suggested_count": 0,
            "applied_count": 0,
            "needs_review_count": 0,
            "skipped_count": 0,
        }
        action_ids: list[str] = []
        for entry in actions[:_MAX_ACTIONS_PER_RUN]:
            parsed = _parse_action(entry)
            if not parsed:
                counts["skipped_count"] += 1
                continue
            result = await self._handle_action(
                session,
                organization_id=organization_id,
                project_id=project_id,
                chapter=chapter,
                scene=scene,
                draft=draft,
                created_by=created_by,
                action=parsed,
            )
            action_ids.append(str(result.get("action_id") or ""))
            status = str(result.get("status") or "skipped")
            if status == "applied":
                counts["applied_count"] += 1
            elif status == "needs_review":
                counts["needs_review_count"] += 1
            elif status == "suggested":
                counts["suggested_count"] += 1
            else:
                counts["skipped_count"] += 1
        return {
            **counts,
            "action_count": len([item for item in action_ids if item]),
            "action_ids": [item for item in action_ids if item],
        }

    async def _load_story_states(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
    ) -> list[StoryStateItem]:
        rows = list(
            await StoryStateRepository(session).list_filtered(
                organization_id=organization_id,
                project_id=project_id,
                limit=120,
            )
        )
        return [row for row in rows if (row.status or "active") != "inactive"]

    async def _load_open_issues(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
        scene_id: str,
    ) -> list[ContinuityIssue]:
        stmt = (
            select(ContinuityIssue)
            .where(
                ContinuityIssue.organization_id == organization_id,
                ContinuityIssue.project_id == project_id,
                ContinuityIssue.status == "open",
                or_(
                    ContinuityIssue.scene_id == scene_id,
                    and_(
                        ContinuityIssue.chapter_id == chapter_id,
                        ContinuityIssue.scene_id.is_(None),
                    ),
                ),
            )
            .order_by(ContinuityIssue.updated_at.desc())
            .limit(30)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    def _prompt_payload(
        self,
        *,
        chapter: Chapter,
        scene: Scene,
        draft: DraftVersion,
        states: list[StoryStateItem],
        requirements: list[ChapterStateRequirement],
        issues: list[ContinuityIssue],
        source: str,
    ) -> dict[str, Any]:
        return {
            "trigger": {
                "source": source,
                "hint": (
                    "audit_scene 表示本次由审稿问题触发，请重点判断审稿问题是正文错误、"
                    "关键设定需更新，还是承接要求已过期。"
                    if source == "audit_scene"
                    else "draft 表示本次由正文生成/重写后触发，请重点判断正文是否改变长期设定。"
                ),
            },
            "chapter": {
                "id": chapter.id,
                "chapter_index": chapter.chapter_index,
                "title": chapter.title,
                "summary": chapter.summary,
                "goal": chapter.goal,
                "conflict": chapter.conflict,
            },
            "scene": {
                "id": scene.id,
                "scene_index": scene.scene_index,
                "title": scene.title,
                "scene_purpose": scene.scene_purpose,
                "entry_state": scene.entry_state,
                "exit_state": scene.exit_state,
                "goal": scene.goal,
                "conflict": scene.conflict,
                "reveal": scene.reveal,
                "hook": scene.hook,
            },
            "draft": {
                "id": draft.id,
                "word_count": draft.word_count,
                "content_excerpt": (draft.content or "")[:9000],
            },
            "story_states": [_state_snapshot(row) for row in states],
            "chapter_requirements": [_requirement_snapshot(row) for row in requirements],
            "continuity_issues": [_issue_payload(row) for row in issues],
            "policy": {
                "auto_apply": "low 且 confidence >= 0.85 可自动应用",
                "medium_auto_apply": (
                    "medium 且 confidence >= 0.88 且支持撤销时可自动应用；"
                    "merge_states 暂不支持中风险自动应用"
                ),
                "high": "high 永远进入 needs_review，不自动改库",
                "id_rule": "只能引用输入中真实存在的 state/requirement/issue id",
                "supersede_state": (
                    "旧关键设定被新关键设定替代时，target_state_id 填新设定，"
                    "source_state_ids 填旧设定"
                ),
                "create_state": (
                    "正文出现新的长期设定且现有 story_states 中没有同义/近义项时，"
                    "可创建新关键设定；如果已有近似设定，优先 update_state/merge_states"
                ),
                "create_requirement": "审稿问题需要后续持续承接时，可基于已有 state 创建承接要求",
            },
        }

    async def _handle_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        draft: DraftVersion,
        created_by: str | None,
        action: _ParsedAction,
    ) -> dict[str, Any]:
        auto_decision = _policy_decision_for_action(action)
        status = str(auto_decision["status"])
        before_json: dict[str, Any] = {}
        after_json: dict[str, Any] = {}
        validation_error: str | None = None
        applied_at: datetime | None = None
        target_state_id: str | None = None
        target_requirement_id: str | None = None

        try:
            if action.action_type == "create_state":
                proposed = self._proposed_state_payload(
                    chapter=chapter,
                    scene=scene,
                    draft=draft,
                    action=action,
                )
                existing = await self._find_existing_state_candidate(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    proposed=proposed,
                )
                if existing:
                    target_state_id = existing.id
                    before_json = {"target": _state_snapshot(existing)}
                    after_json = {
                        "target": _state_snapshot(existing),
                        "proposed_state": proposed,
                    }
                    validation_error = "similar_state_exists"
                    status = "skipped"
                elif status == "applied":
                    after_json = await self._apply_create_state(
                        session,
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter=chapter,
                        scene=scene,
                        draft=draft,
                        action=action,
                        created_by=created_by,
                    )
                    target_state_id = _clean_id(_json_dict(after_json.get("target")).get("id"))
                    applied_at = _now()
                else:
                    after_json = {"proposed_state": proposed}
            elif action.action_type == "update_state":
                target = await self._get_state_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    state_id=action.target_state_id,
                )
                target_state_id = target.id
                before_json = {"target": _state_snapshot(target)}
                if status == "applied":
                    after_json = await self._apply_update_state(
                        session,
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter=chapter,
                        scene=scene,
                        state=target,
                        action=action,
                        created_by=created_by,
                    )
                    applied_at = _now()
                else:
                    after_json = before_json
            elif action.action_type == "merge_states":
                target = await self._get_state_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    state_id=action.target_state_id,
                )
                target_state_id = target.id
                sources = await self._get_source_states_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    target_state_id=target.id,
                    source_state_ids=action.source_state_ids,
                )
                before_json = {
                    "target": _state_snapshot(target),
                    "sources": [_state_snapshot(row) for row in sources],
                }
                if status == "applied":
                    after_json = await self._apply_merge_states(
                        session,
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter=chapter,
                        scene=scene,
                        target=target,
                        sources=sources,
                        action=action,
                        created_by=created_by,
                    )
                    applied_at = _now()
                else:
                    after_json = before_json
            elif action.action_type == "supersede_state":
                target = await self._get_state_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    state_id=action.target_state_id,
                )
                target_state_id = target.id
                sources = await self._get_source_states_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    target_state_id=target.id,
                    source_state_ids=action.source_state_ids,
                )
                requirements = await self._load_active_requirements_for_states(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    state_ids=[source.id for source in sources],
                )
                before_json = {
                    "target": _state_snapshot(target),
                    "sources": [_state_snapshot(row) for row in sources],
                    "requirements": [_requirement_snapshot(row) for row in requirements],
                }
                if status == "applied":
                    after_json = await self._apply_supersede_states(
                        session,
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter=chapter,
                        scene=scene,
                        target=target,
                        sources=sources,
                        requirements=requirements,
                        action=action,
                        created_by=created_by,
                    )
                    applied_at = _now()
                else:
                    after_json = before_json
            elif action.action_type == "create_requirement":
                issue = await self._get_issue_from_patch_or_none(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    action=action,
                )
                state_id = action.target_state_id or (issue.story_state_item_id if issue else None)
                target = await self._get_state_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    state_id=state_id,
                )
                target_state_id = target.id
                before_json = {}
                if status == "applied":
                    after_json = await self._apply_create_requirement(
                        session,
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter=chapter,
                        scene=scene,
                        state=target,
                        action=action,
                        issue=issue,
                        created_by=created_by,
                    )
                    target_requirement_id = _clean_id(
                        _json_dict(after_json.get("requirement")).get("id")
                    )
                    applied_at = _now()
                else:
                    after_json = {
                        "proposed_requirement": self._proposed_requirement_payload(
                            chapter=chapter,
                            scene=scene,
                            state=target,
                            action=action,
                            issue=issue,
                        )
                    }
            elif action.action_type == "resolve_requirement":
                requirement = await self._get_requirement_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    requirement_id=action.target_requirement_id,
                )
                target_requirement_id = requirement.id
                target_state_id = requirement.state_item_id
                before_json = {"requirement": _requirement_snapshot(requirement)}
                if status == "applied":
                    after_json = await self._apply_requirement_status(
                        session,
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter=chapter,
                        scene=scene,
                        requirement=requirement,
                        action=action,
                        status="resolved",
                        superseded_by_requirement_id=None,
                        created_by=created_by,
                    )
                    applied_at = _now()
                else:
                    after_json = before_json
            elif action.action_type == "supersede_requirement":
                requirement = await self._get_requirement_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    requirement_id=action.target_requirement_id,
                )
                replacement_id = await self._validate_replacement_requirement(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    target_requirement_id=requirement.id,
                    replacement_requirement_id=action.superseded_by_requirement_id,
                )
                target_requirement_id = requirement.id
                target_state_id = requirement.state_item_id
                before_json = {"requirement": _requirement_snapshot(requirement)}
                if status == "applied":
                    after_json = await self._apply_requirement_status(
                        session,
                        organization_id=organization_id,
                        project_id=project_id,
                        chapter=chapter,
                        scene=scene,
                        requirement=requirement,
                        action=action,
                        status="superseded",
                        superseded_by_requirement_id=replacement_id,
                        created_by=created_by,
                    )
                    applied_at = _now()
                else:
                    after_json = before_json
            else:
                validation_error = "unsupported_action_type"
                status = "skipped"
        except ValueError as exc:
            validation_error = str(exc)
            status = "skipped"
            after_json = before_json

        reason = action.reason
        if validation_error:
            reason = f"{reason}；跳过原因：{validation_error}" if reason else validation_error
        row = await StoryStateMaintenanceActionRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            draft_id=draft.id,
            action_type=action.action_type,
            target_state_id=target_state_id,
            source_state_ids=list(action.source_state_ids),
            target_requirement_id=target_requirement_id,
            risk_level=action.risk_level,
            confidence=action.confidence,
            status=status,
            reason=reason,
            patch_json=_patch_json_for_action(action, auto_decision=auto_decision),
            before_json=before_json,
            after_json=after_json,
            created_by=created_by,
            applied_at=applied_at,
        )
        if status == "applied":
            future_result = await self._apply_future_requirements_for_action(
                session,
                organization_id=organization_id,
                project_id=project_id,
                chapter=chapter,
                scene=scene,
                action_row=row,
                parsed=action,
                created_by=created_by,
            )
            if future_result:
                row.after_json = {**dict(row.after_json or {}), **future_result}
                await session.flush()
        return {"action_id": row.id, "status": status}

    async def _get_state_or_error(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        state_id: str | None,
    ) -> StoryStateItem:
        if not state_id:
            raise ValueError("target_state_id_required")
        state = await StoryStateRepository(session).get(
            state_id,
            organization_id=organization_id,
        )
        if not state or state.project_id != project_id:
            raise ValueError("target_state_not_found")
        return state

    async def _get_source_states_or_error(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        target_state_id: str,
        source_state_ids: list[str],
    ) -> list[StoryStateItem]:
        if not source_state_ids:
            raise ValueError("source_state_ids_required")
        if target_state_id in source_state_ids:
            raise ValueError("cannot_merge_state_into_self")
        rows: list[StoryStateItem] = []
        for state_id in source_state_ids:
            rows.append(
                await self._get_state_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    state_id=state_id,
                )
            )
        return rows

    async def _load_active_requirements_for_states(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        state_ids: list[str],
    ) -> list[ChapterStateRequirement]:
        state_ids = _dedupe_ids(state_ids)
        if not state_ids:
            return []
        result = await session.execute(
            select(ChapterStateRequirement).where(
                ChapterStateRequirement.organization_id == organization_id,
                ChapterStateRequirement.project_id == project_id,
                ChapterStateRequirement.state_item_id.in_(state_ids),
                ChapterStateRequirement.status == "active",
            )
        )
        return list(result.scalars().all())

    async def _get_requirement_or_error(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        requirement_id: str | None,
    ) -> ChapterStateRequirement:
        if not requirement_id:
            raise ValueError("target_requirement_id_required")
        requirement = await ChapterStateRequirementRepository(session).get(
            requirement_id,
            organization_id=organization_id,
        )
        if not requirement or requirement.project_id != project_id:
            raise ValueError("target_requirement_not_found")
        return requirement

    async def _validate_replacement_requirement(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        target_requirement_id: str,
        replacement_requirement_id: str | None,
    ) -> str | None:
        if not replacement_requirement_id:
            return None
        if replacement_requirement_id == target_requirement_id:
            raise ValueError("cannot_supersede_requirement_by_self")
        replacement = await self._get_requirement_or_error(
            session,
            organization_id=organization_id,
            project_id=project_id,
            requirement_id=replacement_requirement_id,
        )
        return replacement.id

    def _parsed_action_from_row(
        self,
        action: StoryStateMaintenanceAction,
    ) -> _ParsedAction:
        patch = _json_dict(action.patch_json)
        return _ParsedAction(
            action_type=action.action_type,
            target_state_id=action.target_state_id,
            source_state_ids=_dedupe_ids(_json_list(action.source_state_ids)),
            target_requirement_id=action.target_requirement_id,
            superseded_by_requirement_id=_clean_id(patch.get("superseded_by_requirement_id")),
            risk_level=action.risk_level or "low",
            confidence=_float_between_zero_and_one(action.confidence),
            reason=action.reason or "manual_apply_ai_story_state_maintenance",
            patch=patch,
        )

    async def _load_action_chapter(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str | None,
    ) -> Chapter:
        if not chapter_id:
            raise ConflictError("story_state_maintenance_action_chapter_missing")
        result = await session.execute(
            select(Chapter).where(
                Chapter.organization_id == organization_id,
                Chapter.project_id == project_id,
                Chapter.id == chapter_id,
            )
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise ConflictError("story_state_maintenance_action_chapter_not_found")
        return chapter

    async def _load_action_scene(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        scene_id: str | None,
    ) -> Scene:
        if not scene_id:
            raise ConflictError("story_state_maintenance_action_scene_missing")
        result = await session.execute(
            select(Scene).where(
                Scene.organization_id == organization_id,
                Scene.project_id == project_id,
                Scene.id == scene_id,
            )
        )
        scene = result.scalar_one_or_none()
        if not scene:
            raise ConflictError("story_state_maintenance_action_scene_not_found")
        return scene

    async def _get_issue_from_patch_or_none(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: _ParsedAction,
    ) -> ContinuityIssue | None:
        source_issue_id = _clean_id(action.patch.get("source_issue_id"))
        if not source_issue_id:
            return None
        result = await session.execute(
            select(ContinuityIssue).where(
                ContinuityIssue.organization_id == organization_id,
                ContinuityIssue.project_id == project_id,
                ContinuityIssue.id == source_issue_id,
            )
        )
        issue = result.scalar_one_or_none()
        if not issue:
            raise ValueError("source_issue_not_found")
        return issue

    def _proposed_state_payload(
        self,
        *,
        chapter: Chapter,
        scene: Scene,
        draft: DraftVersion | None,
        action: _ParsedAction,
    ) -> dict[str, Any]:
        patch = action.patch
        entity_type = _clean_entity_type(patch.get("entity_type"))
        state_type = _clean_state_type(patch.get("state_type"))
        name = _clean_text(patch.get("name"))
        summary = _clean_text(patch.get("summary"))
        if not entity_type:
            raise ValueError("state_entity_type_required")
        if not state_type:
            raise ValueError("state_type_required")
        if not name:
            raise ValueError("state_name_required")
        if not summary:
            raise ValueError("state_summary_required")

        status = _clean_text(patch.get("status")) or "active"
        if status not in _ALLOWED_STATE_STATUSES:
            raise ValueError("unsafe_state_status_patch")
        value_json = patch.get("value_json") if isinstance(patch.get("value_json"), dict) else {}
        source_excerpt = _clean_text(patch.get("source_excerpt")) or (
            (draft.content or "")[:300] if draft else ""
        )
        return {
            "entity_type": entity_type,
            "entity_id": _clean_id(patch.get("entity_id")),
            "state_type": state_type,
            "name": name[:200],
            "status": status,
            "superseded_by_state_id": None,
            "status_reason": _clean_text(patch.get("status_reason")),
            "summary": summary,
            "value_json": dict(value_json),
            "source_chapter_id": chapter.id,
            "source_scene_id": scene.id,
            "source_excerpt": source_excerpt[:300],
            "updated_in_chapter_id": chapter.id,
            "priority": max(0, _safe_int(patch.get("priority"), 85)),
            "is_hard_constraint": (
                bool(patch["is_hard_constraint"])
                if isinstance(patch.get("is_hard_constraint"), bool)
                else True
            ),
        }

    async def _find_existing_state_candidate(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        proposed: dict[str, Any],
    ) -> StoryStateItem | None:
        entity_type = _clean_entity_type(proposed.get("entity_type"))
        state_type = _clean_state_type(proposed.get("state_type"))
        name = _clean_text(proposed.get("name"))
        if not entity_type or not state_type or not name:
            return None

        stmt = select(StoryStateItem).where(
            StoryStateItem.organization_id == organization_id,
            StoryStateItem.project_id == project_id,
            StoryStateItem.entity_type == entity_type,
            StoryStateItem.state_type == state_type,
            StoryStateItem.status != "inactive",
        )
        entity_id = _clean_id(proposed.get("entity_id"))
        if entity_id:
            stmt = stmt.where(StoryStateItem.entity_id == entity_id)
        else:
            stmt = stmt.where(StoryStateItem.entity_id.is_(None))
        result = await session.execute(stmt.limit(80))
        proposed_name_key = _compact_match_text(name)
        proposed_summary_key = _compact_match_text(proposed.get("summary"))
        for row in result.scalars().all():
            row_name_key = _compact_match_text(row.name)
            if row_name_key and row_name_key == proposed_name_key:
                return row
            row_summary_key = _compact_match_text(row.summary)
            if (
                proposed_summary_key
                and row_summary_key
                and proposed_summary_key == row_summary_key
            ):
                return row
        return None

    async def _apply_create_state(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        draft: DraftVersion | None,
        action: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        proposed = self._proposed_state_payload(
            chapter=chapter,
            scene=scene,
            draft=draft,
            action=action,
        )
        existing = await self._find_existing_state_candidate(
            session,
            organization_id=organization_id,
            project_id=project_id,
            proposed=proposed,
        )
        if existing:
            raise ValueError("similar_state_exists")

        state = await StoryStateRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            entity_type=str(proposed["entity_type"]),
            entity_id=proposed.get("entity_id"),
            state_type=str(proposed["state_type"]),
            name=str(proposed["name"]),
            status=str(proposed["status"]),
            superseded_by_state_id=None,
            status_reason=str(proposed.get("status_reason") or ""),
            summary=str(proposed["summary"]),
            value_json=dict(proposed.get("value_json") or {}),
            source_chapter_id=chapter.id,
            source_scene_id=scene.id,
            source_excerpt=str(proposed.get("source_excerpt") or ""),
            updated_in_chapter_id=chapter.id,
            priority=int(proposed["priority"]),
            is_hard_constraint=bool(proposed["is_hard_constraint"]),
        )
        after = _state_snapshot(state)
        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=state.id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            change_type="create",
            before_json={},
            after_json=after,
            reason=f"ai_story_state_maintenance:{action.reason}",
            source_excerpt=state.source_excerpt,
            created_by=created_by,
        )
        return {"target": after}

    def _future_requirement_payload(
        self,
        *,
        action: _ParsedAction,
        state: StoryStateItem,
    ) -> dict[str, Any] | None:
        raw = action.patch.get("future_requirement")
        config = dict(raw) if isinstance(raw, dict) else {}
        if config.get("enabled") is False:
            return None

        summary = (
            _clean_text(config.get("summary"))
            or _clean_text(action.patch.get("future_requirement_summary"))
        )
        if not summary:
            return None

        scope = _clean_text(config.get("scope") or action.patch.get("future_requirement_scope"))
        scope_default = {
            "next_chapter": 1,
            "next_3_chapters": 3,
            "short_term": 3,
            "long_term": _FUTURE_REQUIREMENT_MAX_CHAPTER_COUNT,
            "until_payoff": _FUTURE_REQUIREMENT_MAX_CHAPTER_COUNT,
        }.get(scope, _FUTURE_REQUIREMENT_DEFAULT_CHAPTER_COUNT)
        chapter_count = _bounded_future_chapter_count(
            config.get("chapter_count")
            or config.get("target_chapter_count")
            or action.patch.get("future_chapter_count"),
            default=scope_default,
        )
        priority = max(
            0,
            min(
                100,
                _safe_int(
                    config.get("priority") or action.patch.get("future_requirement_priority"),
                    max(85, int(state.priority or 0)),
                ),
            ),
        )
        return {
            "requirement_type": _clean_requirement_type(
                config.get("requirement_type")
                or action.patch.get("future_requirement_type")
                or "must_remember"
            ),
            "summary": summary[:1000],
            "priority": priority,
            "chapter_count": chapter_count,
            "scope": scope or "auto",
        }

    async def _load_future_unwritten_chapters(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        limit: int,
    ) -> list[Chapter]:
        generated_draft_exists = (
            select(DraftVersion.id)
            .where(
                DraftVersion.organization_id == organization_id,
                DraftVersion.project_id == project_id,
                DraftVersion.chapter_id == Chapter.id,
                DraftVersion.content != "",
            )
            .exists()
        )
        result = await session.execute(
            select(Chapter)
            .where(
                Chapter.organization_id == organization_id,
                Chapter.project_id == project_id,
                Chapter.chapter_index > int(chapter.chapter_index or 0),
                Chapter.status.notin_(["drafted", "completed", "exported"]),
                ~generated_draft_exists,
            )
            .order_by(Chapter.chapter_index.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _find_existing_future_requirement(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
        state_item_id: str,
        requirement_type: str,
        summary: str,
    ) -> ChapterStateRequirement | None:
        result = await session.execute(
            select(ChapterStateRequirement).where(
                ChapterStateRequirement.organization_id == organization_id,
                ChapterStateRequirement.project_id == project_id,
                ChapterStateRequirement.chapter_id == chapter_id,
                ChapterStateRequirement.state_item_id == state_item_id,
                ChapterStateRequirement.requirement_type == requirement_type,
                ChapterStateRequirement.summary == summary,
                ChapterStateRequirement.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def _apply_future_requirements_for_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        action_row: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        if parsed.action_type not in _FUTURE_REQUIREMENT_ACTION_TYPES:
            return {}
        state_id = action_row.target_state_id or parsed.target_state_id
        if not state_id:
            return {}
        try:
            state = await self._get_state_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                state_id=state_id,
            )
        except ValueError:
            return {}
        payload = self._future_requirement_payload(action=parsed, state=state)
        if not payload:
            return {}

        future_chapters = await self._load_future_unwritten_chapters(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            limit=int(payload["chapter_count"]),
        )
        if not future_chapters:
            return {}

        reason = f"{_FUTURE_REQUIREMENT_REASON_PREFIX}{action_row.id}"
        created: list[ChapterStateRequirement] = []
        deduped = 0
        repo = ChapterStateRequirementRepository(session)
        history_repo = StoryStateHistoryRepository(session)
        for target_chapter in future_chapters:
            existing = await self._find_existing_future_requirement(
                session,
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=target_chapter.id,
                state_item_id=state.id,
                requirement_type=str(payload["requirement_type"]),
                summary=str(payload["summary"]),
            )
            if existing:
                deduped += 1
                continue
            requirement = await repo.create(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=target_chapter.id,
                source_chapter_id=chapter.id,
                source_scene_id=scene.id,
                target_chapter_id=target_chapter.id,
                origin_type="previous_chapter_carryover",
                status="active",
                superseded_by_requirement_id=None,
                source_issue_id=None,
                status_reason=reason,
                state_item_id=state.id,
                requirement_type=str(payload["requirement_type"]),
                summary=str(payload["summary"]),
                priority=int(payload["priority"]),
            )
            created.append(requirement)
            snapshot = _requirement_snapshot(requirement)
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=state.id,
                chapter_id=target_chapter.id,
                scene_id=scene.id,
                change_type="create",
                before_json={},
                after_json={"requirement": snapshot},
                reason=reason,
                source_excerpt=state.source_excerpt,
                created_by=created_by,
            )

        if not created and not deduped:
            return {}
        return {
            "future_requirement_count": len(created),
            "future_requirement_deduped_count": deduped,
            "future_requirement_scope": payload["scope"],
            "future_requirements": [_requirement_snapshot(row) for row in created],
        }

    def _proposed_requirement_payload(
        self,
        *,
        chapter: Chapter,
        scene: Scene,
        state: StoryStateItem,
        action: _ParsedAction,
        issue: ContinuityIssue | None,
    ) -> dict[str, Any]:
        patch = action.patch
        summary = (
            _clean_text(patch.get("summary"))
            or _clean_text(issue.suggested_fix if issue else "")
            or _clean_text(action.reason)
        )
        return {
            "chapter_id": chapter.id,
            "source_chapter_id": chapter.id,
            "source_scene_id": scene.id,
            "target_chapter_id": chapter.id,
            "origin_type": "current_chapter_extract",
            "status": "active",
            "source_issue_id": issue.id if issue else _clean_id(patch.get("source_issue_id")),
            "state_item_id": state.id,
            "requirement_type": _clean_requirement_type(patch.get("requirement_type")),
            "summary": summary,
            "priority": max(0, _safe_int(patch.get("priority"), _priority_from_issue(issue))),
        }

    async def _find_existing_requirement(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
        state_item_id: str,
        requirement_type: str,
        summary: str,
    ) -> ChapterStateRequirement | None:
        result = await session.execute(
            select(ChapterStateRequirement).where(
                ChapterStateRequirement.organization_id == organization_id,
                ChapterStateRequirement.project_id == project_id,
                ChapterStateRequirement.chapter_id == chapter_id,
                ChapterStateRequirement.state_item_id == state_item_id,
                ChapterStateRequirement.requirement_type == requirement_type,
                ChapterStateRequirement.summary == summary,
            )
        )
        return result.scalar_one_or_none()

    async def _apply_create_requirement(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        state: StoryStateItem,
        action: _ParsedAction,
        issue: ContinuityIssue | None,
        created_by: str | None,
    ) -> dict[str, Any]:
        proposed = self._proposed_requirement_payload(
            chapter=chapter,
            scene=scene,
            state=state,
            action=action,
            issue=issue,
        )
        summary = _clean_text(proposed.get("summary"))
        if not summary:
            raise ValueError("requirement_summary_required")
        existing = await self._find_existing_requirement(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter_id=chapter.id,
            state_item_id=state.id,
            requirement_type=str(proposed["requirement_type"]),
            summary=summary,
        )
        if existing:
            before = _requirement_snapshot(existing)
            if (existing.status or "active") != "active":
                existing.status = "active"
                existing.status_reason = ""
            existing.priority = max(int(existing.priority or 0), int(proposed["priority"]))
            if proposed.get("source_issue_id") and not existing.source_issue_id:
                existing.source_issue_id = str(proposed["source_issue_id"])
            await session.flush()
            after = _requirement_snapshot(existing)
            deduped = True
            requirement = existing
        else:
            before = {}
            requirement = await ChapterStateRequirementRepository(session).create(
                organization_id=organization_id,
                project_id=project_id,
                chapter_id=chapter.id,
                source_chapter_id=chapter.id,
                source_scene_id=scene.id,
                target_chapter_id=chapter.id,
                origin_type="current_chapter_extract",
                status="active",
                superseded_by_requirement_id=None,
                source_issue_id=proposed.get("source_issue_id"),
                status_reason="",
                state_item_id=state.id,
                requirement_type=str(proposed["requirement_type"]),
                summary=summary,
                priority=int(proposed["priority"]),
            )
            after = _requirement_snapshot(requirement)
            deduped = False

        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=state.id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            change_type="create" if not deduped else "update",
            before_json={"requirement": before} if before else {},
            after_json={"requirement": after},
            reason=f"ai_story_state_maintenance:{action.reason}",
            source_excerpt="",
            created_by=created_by,
        )
        return {"requirement": after, "deduped": deduped}

    async def _apply_update_state(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        state: StoryStateItem,
        action: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        before = story_state_service.snapshot(state)
        patch = action.patch
        summary = _clean_text(patch.get("summary"))
        value_patch = patch.get("value_json") if isinstance(patch.get("value_json"), dict) else None
        if isinstance(patch.get("value_json"), dict):
            merged_value = dict(state.value_json or {})
            merged_value.update(dict(patch["value_json"]))
        else:
            merged_value = dict(state.value_json or {})
        status = _clean_text(patch.get("status"))
        if status:
            if status not in _ALLOWED_STATE_STATUSES:
                raise ValueError("unsafe_state_status_patch")
        next_priority = int(state.priority or 0)
        if "priority" in patch:
            try:
                next_priority = max(0, int(patch.get("priority") or 0))
            except (TypeError, ValueError):
                raise ValueError("invalid_priority_patch") from None

        if summary:
            state.summary = summary
        if value_patch is not None:
            state.value_json = merged_value
        if status:
            state.status = status
        state.priority = next_priority
        if isinstance(patch.get("is_hard_constraint"), bool):
            state.is_hard_constraint = bool(patch["is_hard_constraint"])
        source_excerpt = _clean_text(patch.get("source_excerpt"))
        if source_excerpt:
            state.source_excerpt = source_excerpt[:300]
        state.updated_in_chapter_id = chapter.id
        await session.flush()
        after = story_state_service.snapshot(state)
        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=state.id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            change_type="update",
            before_json=before,
            after_json=after,
            reason=f"ai_story_state_maintenance:{action.reason}",
            source_excerpt=state.source_excerpt,
            created_by=created_by,
        )
        return {"target": _state_snapshot(state)}

    async def _apply_merge_states(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        target: StoryStateItem,
        sources: list[StoryStateItem],
        action: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        history_repo = StoryStateHistoryRepository(session)
        before_target = story_state_service.snapshot(target)
        before_sources = {source.id: story_state_service.snapshot(source) for source in sources}
        patch = action.patch

        summary = _clean_text(patch.get("summary"))
        next_priority = max(
            [int(target.priority or 0)] + [int(source.priority or 0) for source in sources]
        )
        if "priority" in patch:
            try:
                next_priority = max(0, int(patch.get("priority") or 0))
            except (TypeError, ValueError):
                raise ValueError("invalid_priority_patch") from None

        if summary:
            target.summary = summary
        elif not _clean_text(target.summary):
            target.summary = next((source.summary for source in sources if source.summary), "")

        patch_value = patch.get("value_json") if isinstance(patch.get("value_json"), dict) else None
        target.value_json = _merge_value_json(dict(target.value_json or {}), sources, patch_value)

        target.priority = next_priority
        if isinstance(patch.get("is_hard_constraint"), bool):
            target.is_hard_constraint = bool(patch["is_hard_constraint"])
        else:
            target.is_hard_constraint = bool(target.is_hard_constraint) or any(
                bool(source.is_hard_constraint) for source in sources
            )
        target.status = "active"
        target.superseded_by_state_id = None
        target.status_reason = ""
        target.updated_in_chapter_id = chapter.id

        for source in sources:
            source.status = "inactive"
            source.superseded_by_state_id = target.id
            source.status_reason = action.reason or "ai_story_state_merge"

        source_ids = [source.id for source in sources]
        requirement_result = await session.execute(
            update(ChapterStateRequirement)
            .where(
                ChapterStateRequirement.organization_id == organization_id,
                ChapterStateRequirement.project_id == project_id,
                ChapterStateRequirement.state_item_id.in_(source_ids),
            )
            .values(state_item_id=target.id)
        )
        issue_result = await session.execute(
            update(ContinuityIssue)
            .where(
                ContinuityIssue.organization_id == organization_id,
                ContinuityIssue.project_id == project_id,
                ContinuityIssue.story_state_item_id.in_(source_ids),
            )
            .values(story_state_item_id=target.id)
        )
        await session.flush()
        await history_repo.create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=target.id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            change_type="update",
            before_json=before_target,
            after_json=story_state_service.snapshot(target),
            reason=f"ai_story_state_maintenance:{action.reason}",
            source_excerpt=target.source_excerpt,
            created_by=created_by,
        )
        for source in sources:
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=source.id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                change_type="resolve",
                before_json=before_sources[source.id],
                after_json=story_state_service.snapshot(source),
                reason=f"ai_story_state_maintenance:{action.reason}",
                source_excerpt=source.source_excerpt,
                created_by=created_by,
            )
        return {
            "target": _state_snapshot(target),
            "sources": [_state_snapshot(source) for source in sources],
            "updated_requirement_count": int(requirement_result.rowcount or 0),
            "updated_issue_count": int(issue_result.rowcount or 0),
        }

    async def _apply_supersede_states(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        target: StoryStateItem,
        sources: list[StoryStateItem],
        requirements: list[ChapterStateRequirement],
        action: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        if (target.status or "active") == "inactive":
            raise ValueError("replacement_state_inactive")

        history_repo = StoryStateHistoryRepository(session)
        before_sources = {source.id: story_state_service.snapshot(source) for source in sources}
        before_requirements = {
            requirement.id: _requirement_snapshot(requirement) for requirement in requirements
        }
        state_reason = (
            _clean_text(action.patch.get("status_reason"))
            or action.reason
            or "ai_story_state_supersede"
        )
        requirement_reason = (
            _clean_text(action.patch.get("requirement_status_reason")) or state_reason
        )

        for source in sources:
            source.status = "inactive"
            source.superseded_by_state_id = target.id
            source.status_reason = state_reason
            source.updated_in_chapter_id = chapter.id

        for requirement in requirements:
            requirement.status = "superseded"
            requirement.superseded_by_requirement_id = None
            requirement.status_reason = requirement_reason

        await session.flush()

        for source in sources:
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=source.id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                change_type="resolve",
                before_json=before_sources[source.id],
                after_json=story_state_service.snapshot(source),
                reason=f"ai_story_state_maintenance:{action.reason}",
                source_excerpt=source.source_excerpt,
                created_by=created_by,
            )

        for requirement in requirements:
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=requirement.state_item_id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                change_type="resolve",
                before_json={"requirement": before_requirements[requirement.id]},
                after_json={"requirement": _requirement_snapshot(requirement)},
                reason=f"ai_story_state_maintenance:{action.reason}",
                source_excerpt="",
                created_by=created_by,
            )

        return {
            "target": _state_snapshot(target),
            "sources": [_state_snapshot(source) for source in sources],
            "requirements": [_requirement_snapshot(requirement) for requirement in requirements],
            "superseded_requirement_count": len(requirements),
        }

    async def _apply_requirement_status(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        requirement: ChapterStateRequirement,
        action: _ParsedAction,
        status: str,
        superseded_by_requirement_id: str | None,
        created_by: str | None,
    ) -> dict[str, Any]:
        before = _requirement_snapshot(requirement)
        requirement.status = status
        requirement.status_reason = (
            _clean_text(action.patch.get("status_reason"))
            or action.reason
            or f"ai_{status}_requirement"
        )
        if status == "superseded":
            requirement.superseded_by_requirement_id = superseded_by_requirement_id
        await session.flush()
        after = _requirement_snapshot(requirement)
        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=requirement.state_item_id,
            chapter_id=chapter.id,
            scene_id=scene.id,
            change_type="resolve" if status in {"resolved", "superseded"} else "update",
            before_json={"requirement": before},
            after_json={"requirement": after},
            reason=f"ai_story_state_maintenance:{action.reason}",
            source_excerpt="",
            created_by=created_by,
        )
        return {"requirement": after}

    async def _apply_logged_create_state_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        action_row: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        result = await self._apply_create_state(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            draft=None,
            action=parsed,
            created_by=created_by,
        )
        action_row.target_state_id = _clean_id(_json_dict(result.get("target")).get("id"))
        return result

    async def _apply_logged_update_state_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        action_row: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        if not parsed.patch:
            raise ConflictError("story_state_maintenance_action_patch_missing")
        target = await self._get_state_for_logged_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=action_row,
        )
        return await self._apply_update_state(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            state=target,
            action=parsed,
            created_by=created_by,
        )

    async def _apply_logged_merge_states_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        action_row: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        target = await self._get_state_for_logged_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=action_row,
        )
        sources = await self._get_source_states_for_logged_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            target_state_id=target.id,
            action=action_row,
            parsed=parsed,
        )
        return await self._apply_merge_states(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            target=target,
            sources=sources,
            action=parsed,
            created_by=created_by,
        )

    async def _apply_logged_supersede_state_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        action_row: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        target = await self._get_state_for_logged_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=action_row,
        )
        sources = await self._get_source_states_for_logged_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            target_state_id=target.id,
            action=action_row,
            parsed=parsed,
        )
        requirements = await self._get_requirements_for_logged_supersede_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=action_row,
        )
        return await self._apply_supersede_states(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            target=target,
            sources=sources,
            requirements=requirements,
            action=parsed,
            created_by=created_by,
        )

    async def _apply_logged_create_requirement_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        action_row: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        issue = await self._get_issue_from_patch_or_none(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=parsed,
        )
        state_id = parsed.target_state_id or (issue.story_state_item_id if issue else None)
        parsed.target_state_id = state_id
        state = await self._get_state_for_logged_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=action_row,
            fallback_state_id=state_id,
            require_before_snapshot=False,
        )
        result = await self._apply_create_requirement(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            state=state,
            action=parsed,
            issue=issue,
            created_by=created_by,
        )
        action_row.target_state_id = state.id
        action_row.target_requirement_id = _clean_id(
            _json_dict(result.get("requirement")).get("id")
        )
        return result

    async def _apply_logged_requirement_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        action_row: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
        created_by: str | None,
    ) -> dict[str, Any]:
        requirement = await self._get_requirement_for_logged_action(
            session,
            organization_id=organization_id,
            project_id=project_id,
            action=action_row,
        )
        if parsed.action_type == "resolve_requirement":
            return await self._apply_requirement_status(
                session,
                organization_id=organization_id,
                project_id=project_id,
                chapter=chapter,
                scene=scene,
                requirement=requirement,
                action=parsed,
                status="resolved",
                superseded_by_requirement_id=None,
                created_by=created_by,
            )
        replacement_id = await self._validate_replacement_requirement(
            session,
            organization_id=organization_id,
            project_id=project_id,
            target_requirement_id=requirement.id,
            replacement_requirement_id=parsed.superseded_by_requirement_id,
        )
        return await self._apply_requirement_status(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            requirement=requirement,
            action=parsed,
            status="superseded",
            superseded_by_requirement_id=replacement_id,
            created_by=created_by,
        )

    async def _get_state_for_logged_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
        fallback_state_id: str | None = None,
        require_before_snapshot: bool = True,
    ) -> StoryStateItem:
        before_snapshot = _json_dict(_json_dict(action.before_json).get("target"))
        state_id = _clean_id(before_snapshot.get("id")) or action.target_state_id
        state_id = state_id or fallback_state_id
        if not state_id:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")
        try:
            state = await self._get_state_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                state_id=state_id,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        if require_before_snapshot and not before_snapshot:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")
        if before_snapshot and not _snapshot_matches_model(
            state,
            before_snapshot,
            _STATE_RESTORE_FIELDS,
        ):
            raise ConflictError("story_state_maintenance_action_target_changed")
        return state

    async def _get_source_states_for_logged_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        target_state_id: str,
        action: StoryStateMaintenanceAction,
        parsed: _ParsedAction,
    ) -> list[StoryStateItem]:
        source_snapshots = {
            _clean_id(snapshot.get("id")): snapshot
            for snapshot in _json_list(_json_dict(action.before_json).get("sources"))
            if isinstance(snapshot, dict)
        }
        try:
            sources = await self._get_source_states_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                target_state_id=target_state_id,
                source_state_ids=parsed.source_state_ids,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        for source in sources:
            snapshot = source_snapshots.get(source.id)
            if snapshot and not _snapshot_matches_model(
                source,
                snapshot,
                _STATE_RESTORE_FIELDS,
            ):
                raise ConflictError("story_state_maintenance_action_target_changed")
        return sources

    async def _get_requirements_for_logged_supersede_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
    ) -> list[ChapterStateRequirement]:
        snapshots = [
            snapshot
            for snapshot in _json_list(_json_dict(action.before_json).get("requirements"))
            if isinstance(snapshot, dict)
        ]
        requirements: list[ChapterStateRequirement] = []
        for snapshot in snapshots:
            requirement_id = _clean_id(snapshot.get("id"))
            if not requirement_id:
                raise ConflictError("story_state_maintenance_action_snapshot_missing")
            try:
                requirement = await self._get_requirement_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    requirement_id=requirement_id,
                )
            except ValueError as exc:
                raise ConflictError(str(exc)) from exc
            if not _snapshot_matches_model(
                requirement,
                snapshot,
                _REQUIREMENT_RESTORE_FIELDS,
            ):
                raise ConflictError("story_state_maintenance_action_target_changed")
            requirements.append(requirement)
        return requirements

    async def _get_requirement_for_logged_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
    ) -> ChapterStateRequirement:
        before_snapshot = _json_dict(_json_dict(action.before_json).get("requirement"))
        requirement_id = _clean_id(before_snapshot.get("id")) or action.target_requirement_id
        if not requirement_id or not before_snapshot:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")
        try:
            requirement = await self._get_requirement_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                requirement_id=requirement_id,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        if not _snapshot_matches_model(
            requirement,
            before_snapshot,
            _REQUIREMENT_RESTORE_FIELDS,
        ):
            raise ConflictError("story_state_maintenance_action_target_changed")
        return requirement

    async def _rollback_future_requirements_for_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
        created_by: str | None,
    ) -> None:
        snapshots = [
            snapshot
            for snapshot in _json_list(_json_dict(action.after_json).get("future_requirements"))
            if isinstance(snapshot, dict)
        ]
        if not snapshots:
            return

        reason = f"{_FUTURE_REQUIREMENT_REASON_PREFIX}{action.id}"
        history_repo = StoryStateHistoryRepository(session)
        for snapshot in snapshots:
            requirement_id = _clean_id(snapshot.get("id"))
            if not requirement_id:
                continue
            try:
                requirement = await self._get_requirement_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    requirement_id=requirement_id,
                )
            except ValueError:
                continue
            if requirement.status != "active" or requirement.status_reason != reason:
                continue
            before = _requirement_snapshot(requirement)
            requirement.status = "disabled"
            requirement.status_reason = f"rollback_ai_story_state_maintenance:{action.id}"
            await session.flush()
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=requirement.state_item_id,
                chapter_id=requirement.chapter_id,
                scene_id=action.scene_id,
                change_type="remove",
                before_json={"requirement": before},
                after_json={"requirement": _requirement_snapshot(requirement)},
                reason=f"rollback_ai_story_state_maintenance:{action.id}",
                source_excerpt="",
                created_by=created_by,
            )

    async def _rollback_create_state_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
        created_by: str | None,
    ) -> None:
        after_snapshot = _json_dict(_json_dict(action.after_json).get("target"))
        state_id = _clean_id(after_snapshot.get("id")) or action.target_state_id
        if not state_id:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")
        try:
            state = await self._get_state_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                state_id=state_id,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        if after_snapshot and not _snapshot_matches_model(
            state,
            after_snapshot,
            _STATE_RESTORE_FIELDS,
        ):
            raise ConflictError("story_state_maintenance_action_target_changed")

        current_snapshot = story_state_service.snapshot(state)
        state.status = "inactive"
        state.status_reason = f"rollback_ai_story_state_maintenance:{action.id}"
        state.superseded_by_state_id = None
        await session.flush()
        restored_snapshot = story_state_service.snapshot(state)
        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=state.id,
            chapter_id=action.chapter_id or state.updated_in_chapter_id,
            scene_id=action.scene_id or state.source_scene_id,
            change_type="remove",
            before_json=current_snapshot,
            after_json=restored_snapshot,
            reason=f"rollback_ai_story_state_maintenance:{action.id}",
            source_excerpt=state.source_excerpt,
            created_by=created_by,
        )

    async def _rollback_update_state_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
        created_by: str | None,
    ) -> None:
        before_snapshot = _json_dict(_json_dict(action.before_json).get("target"))
        after_snapshot = _json_dict(_json_dict(action.after_json).get("target"))
        state_id = _clean_id(before_snapshot.get("id")) or action.target_state_id
        if not state_id or not before_snapshot:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")
        try:
            state = await self._get_state_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                state_id=state_id,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        if after_snapshot and not _snapshot_matches_model(
            state,
            after_snapshot,
            _STATE_RESTORE_FIELDS,
        ):
            raise ConflictError("story_state_maintenance_action_target_changed")

        current_snapshot = story_state_service.snapshot(state)
        _restore_model_snapshot(state, before_snapshot, _STATE_RESTORE_FIELDS)
        await session.flush()
        restored_snapshot = story_state_service.snapshot(state)
        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=state.id,
            chapter_id=action.chapter_id or state.updated_in_chapter_id,
            scene_id=action.scene_id or state.source_scene_id,
            change_type="update",
            before_json=current_snapshot,
            after_json=restored_snapshot,
            reason=f"rollback_ai_story_state_maintenance:{action.id}",
            source_excerpt=state.source_excerpt,
            created_by=created_by,
        )

    async def _rollback_supersede_state_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
        created_by: str | None,
    ) -> None:
        before_source_snapshots = [
            snapshot
            for snapshot in _json_list(_json_dict(action.before_json).get("sources"))
            if isinstance(snapshot, dict)
        ]
        after_source_snapshots = {
            _clean_id(snapshot.get("id")): snapshot
            for snapshot in _json_list(_json_dict(action.after_json).get("sources"))
            if isinstance(snapshot, dict)
        }
        before_requirement_snapshots = [
            snapshot
            for snapshot in _json_list(_json_dict(action.before_json).get("requirements"))
            if isinstance(snapshot, dict)
        ]
        after_requirement_snapshots = {
            _clean_id(snapshot.get("id")): snapshot
            for snapshot in _json_list(_json_dict(action.after_json).get("requirements"))
            if isinstance(snapshot, dict)
        }
        if not before_source_snapshots:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")

        states: list[tuple[StoryStateItem, dict[str, Any], dict[str, Any]]] = []
        for before_snapshot in before_source_snapshots:
            state_id = _clean_id(before_snapshot.get("id"))
            if not state_id:
                raise ConflictError("story_state_maintenance_action_snapshot_missing")
            try:
                state = await self._get_state_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    state_id=state_id,
                )
            except ValueError as exc:
                raise ConflictError(str(exc)) from exc
            after_snapshot = after_source_snapshots.get(state.id)
            if after_snapshot and not _snapshot_matches_model(
                state,
                after_snapshot,
                _STATE_RESTORE_FIELDS,
            ):
                raise ConflictError("story_state_maintenance_action_target_changed")
            states.append((state, story_state_service.snapshot(state), before_snapshot))

        requirements: list[
            tuple[ChapterStateRequirement, dict[str, Any], dict[str, Any]]
        ] = []
        for before_snapshot in before_requirement_snapshots:
            requirement_id = _clean_id(before_snapshot.get("id"))
            if not requirement_id:
                raise ConflictError("story_state_maintenance_action_snapshot_missing")
            try:
                requirement = await self._get_requirement_or_error(
                    session,
                    organization_id=organization_id,
                    project_id=project_id,
                    requirement_id=requirement_id,
                )
            except ValueError as exc:
                raise ConflictError(str(exc)) from exc
            after_snapshot = after_requirement_snapshots.get(requirement.id)
            if after_snapshot and not _snapshot_matches_model(
                requirement,
                after_snapshot,
                _REQUIREMENT_RESTORE_FIELDS,
            ):
                raise ConflictError("story_state_maintenance_action_target_changed")
            requirements.append(
                (requirement, _requirement_snapshot(requirement), before_snapshot)
            )

        for state, _, before_snapshot in states:
            _restore_model_snapshot(state, before_snapshot, _STATE_RESTORE_FIELDS)
        for requirement, _, before_snapshot in requirements:
            _restore_model_snapshot(
                requirement,
                before_snapshot,
                _REQUIREMENT_RESTORE_FIELDS,
            )
        await session.flush()

        history_repo = StoryStateHistoryRepository(session)
        for state, current_snapshot, _ in states:
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=state.id,
                chapter_id=action.chapter_id or state.updated_in_chapter_id,
                scene_id=action.scene_id or state.source_scene_id,
                change_type="update",
                before_json=current_snapshot,
                after_json=story_state_service.snapshot(state),
                reason=f"rollback_ai_story_state_maintenance:{action.id}",
                source_excerpt=state.source_excerpt,
                created_by=created_by,
            )
        for requirement, current_snapshot, _ in requirements:
            await history_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                state_item_id=requirement.state_item_id,
                chapter_id=action.chapter_id or requirement.chapter_id,
                scene_id=action.scene_id,
                change_type="update",
                before_json={"requirement": current_snapshot},
                after_json={"requirement": _requirement_snapshot(requirement)},
                reason=f"rollback_ai_story_state_maintenance:{action.id}",
                source_excerpt="",
                created_by=created_by,
            )

    async def _rollback_create_requirement_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
        created_by: str | None,
    ) -> None:
        after_snapshot = _json_dict(_json_dict(action.after_json).get("requirement"))
        requirement_id = _clean_id(after_snapshot.get("id")) or action.target_requirement_id
        if not requirement_id:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")
        try:
            requirement = await self._get_requirement_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                requirement_id=requirement_id,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        if after_snapshot and not _snapshot_matches_model(
            requirement,
            after_snapshot,
            _REQUIREMENT_RESTORE_FIELDS,
        ):
            raise ConflictError("story_state_maintenance_action_target_changed")

        current_snapshot = _requirement_snapshot(requirement)
        requirement.status = "disabled"
        requirement.status_reason = f"rollback_ai_story_state_maintenance:{action.id}"
        await session.flush()
        restored_snapshot = _requirement_snapshot(requirement)
        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=requirement.state_item_id,
            chapter_id=action.chapter_id or requirement.chapter_id,
            scene_id=action.scene_id,
            change_type="remove",
            before_json={"requirement": current_snapshot},
            after_json={"requirement": restored_snapshot},
            reason=f"rollback_ai_story_state_maintenance:{action.id}",
            source_excerpt="",
            created_by=created_by,
        )

    async def _rollback_requirement_action(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        action: StoryStateMaintenanceAction,
        created_by: str | None,
    ) -> None:
        before_snapshot = _json_dict(_json_dict(action.before_json).get("requirement"))
        after_snapshot = _json_dict(_json_dict(action.after_json).get("requirement"))
        requirement_id = _clean_id(before_snapshot.get("id")) or action.target_requirement_id
        if not requirement_id or not before_snapshot:
            raise ConflictError("story_state_maintenance_action_snapshot_missing")
        try:
            requirement = await self._get_requirement_or_error(
                session,
                organization_id=organization_id,
                project_id=project_id,
                requirement_id=requirement_id,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        if after_snapshot and not _snapshot_matches_model(
            requirement,
            after_snapshot,
            _REQUIREMENT_RESTORE_FIELDS,
        ):
            raise ConflictError("story_state_maintenance_action_target_changed")

        current_snapshot = _requirement_snapshot(requirement)
        _restore_model_snapshot(requirement, before_snapshot, _REQUIREMENT_RESTORE_FIELDS)
        await session.flush()
        restored_snapshot = _requirement_snapshot(requirement)
        await StoryStateHistoryRepository(session).create(
            organization_id=organization_id,
            project_id=project_id,
            state_item_id=requirement.state_item_id,
            chapter_id=action.chapter_id or requirement.chapter_id,
            scene_id=action.scene_id,
            change_type="update",
            before_json={"requirement": current_snapshot},
            after_json={"requirement": restored_snapshot},
            reason=f"rollback_ai_story_state_maintenance:{action.id}",
            source_excerpt="",
            created_by=created_by,
        )


story_state_maintainer_service = StoryStateMaintainerService()

__all__ = ["StoryStateMaintainerService", "story_state_maintainer_service"]
