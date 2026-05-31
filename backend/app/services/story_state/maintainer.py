"""AI 关键设定维护器。

正文生成/重写后，基于最新 draft 自动判断哪些长期设定需要轻量维护。
MVP 只自动应用“低风险 + 高置信”的动作，其余写入动作日志，避免打断主流程。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.chapter_state_requirement import ChapterStateRequirement
from app.models.continuity_issue import ContinuityIssue
from app.models.draft_version import DraftVersion
from app.models.scene import Scene
from app.models.story_state_item import StoryStateItem
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
    "update_state",
    "merge_states",
    "resolve_requirement",
    "supersede_requirement",
}
_ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
_AUTO_APPLY_CONFIDENCE = 0.85
_SUGGEST_ONLY_CONFIDENCE = 0.75
_MAX_ACTIONS_PER_RUN = 20
_ALLOWED_STATE_STATUSES = {"active", "hidden", "damaged", "resolved", "consumed"}


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
    if action.risk_level != "low":
        return "needs_review"
    if action.confidence >= _AUTO_APPLY_CONFIDENCE:
        return "applied"
    if action.confidence < _SUGGEST_ONLY_CONFIDENCE:
        return "suggested"
    return "suggested"


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
        if not states and not requirements and not issues:
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
                "auto_apply": "仅 low 且 confidence >= 0.85 可自动应用",
                "medium_high": "medium/high 只记录 needs_review，不自动改库",
                "id_rule": "只能引用输入中真实存在的 id，不能创造 id",
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
        status = _status_for_policy(action)
        before_json: dict[str, Any] = {}
        after_json: dict[str, Any] = {}
        validation_error: str | None = None
        applied_at: datetime | None = None
        target_state_id: str | None = None
        target_requirement_id: str | None = None

        try:
            if action.action_type == "update_state":
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
            before_json=before_json,
            after_json=after_json,
            created_by=created_by,
            applied_at=applied_at,
        )
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


story_state_maintainer_service = StoryStateMaintainerService()

__all__ = ["StoryStateMaintainerService", "story_state_maintainer_service"]
