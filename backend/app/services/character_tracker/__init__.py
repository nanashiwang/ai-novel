"""人物字段版本链追踪服务。

集中处理所有 character 字段修改（手动 / Copilot 提案 / AI 自动推演），
统一落到 character_revisions 表，然后按需应用到 characters 表。

设计要点：
- ContextBuilder 永远只读 status='applied' 的 revision；pending 不进 prompt
- user_edit 来源跳过 pending，直接 applied（保持手动编辑即时生效）
- ai_inferred 来源默认 pending，需用户审核
- 任何 apply 操作都把同 (character_id, field) 的旧 applied 标 superseded
- 同 (character_id, field) 的旧 pending 在新 revision 创建时也标 superseded
- 回滚：把目标历史 revision 重新 apply

字段白名单见 CHARACTER_REVISION_FIELDS。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.character import Character
from app.models.character_revision import CharacterRevision
from app.repositories import CharacterRepository, CharacterRevisionRepository

# 允许走版本链的字段；与 Character ORM 列对齐
CHARACTER_REVISION_FIELDS: Final[set[str]] = {
    "name",
    "role",
    "description",
    "personality",
    "motivation",
    "secret",
    "arc",
    "relationships",
    "current_state",
}

RevisionSource = str  # "user_edit" | "copilot" | "ai_inferred"


def _read_field(character: Character, field: str) -> Any:
    return getattr(character, field)


def _write_field(character: Character, field: str, value: Any) -> None:
    setattr(character, field, value)


def _diff_fields(
    character: Character, new_values: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    """返回 (field, old, new) 列表，仅含真实变化的字段。"""
    changes: list[tuple[str, Any, Any]] = []
    for field, new_value in new_values.items():
        if field not in CHARACTER_REVISION_FIELDS:
            continue
        old_value = _read_field(character, field)
        if old_value != new_value:
            changes.append((field, old_value, new_value))
    return changes


class CharacterTrackerService:
    async def _supersede_pending(
        self,
        session: AsyncSession,
        *,
        character_id: str,
        field: str,
    ) -> None:
        """同一字段产生新 revision 时，把旧 pending 标 superseded。"""
        stmt = select(CharacterRevision).where(
            CharacterRevision.character_id == character_id,
            CharacterRevision.field == field,
            CharacterRevision.status == "pending",
        )
        for old in (await session.execute(stmt)).scalars().all():
            old.status = "superseded"
        await session.flush()

    async def _supersede_applied(
        self,
        session: AsyncSession,
        *,
        character_id: str,
        field: str,
        except_id: str | None = None,
    ) -> None:
        """同一字段新增 applied 后，把旧 applied 标 superseded，保证只有一条权威。"""
        stmt = select(CharacterRevision).where(
            CharacterRevision.character_id == character_id,
            CharacterRevision.field == field,
            CharacterRevision.status == "applied",
        )
        if except_id is not None:
            stmt = stmt.where(CharacterRevision.id != except_id)
        for old in (await session.execute(stmt)).scalars().all():
            old.status = "superseded"
        await session.flush()
        await session.flush()

    async def record_user_edit(
        self,
        session: AsyncSession,
        *,
        character: Character,
        new_values: dict[str, Any],
        created_by: str,
    ) -> list[CharacterRevision]:
        """记录手动编辑：每个变化字段产生一条 source='user_edit' status='applied' 记录，
        同时把新值写入 characters 表。"""
        changes = _diff_fields(character, new_values)
        if not changes:
            return []
        revisions: list[CharacterRevision] = []
        repo = CharacterRevisionRepository(session)
        now = datetime.now(timezone.utc)
        for field, old_value, new_value in changes:
            await self._supersede_pending(
                session, character_id=character.id, field=field
            )
            await self._supersede_applied(
                session, character_id=character.id, field=field
            )
            revision = await repo.create(
                organization_id=character.organization_id,
                project_id=character.project_id,
                character_id=character.id,
                field=field,
                old_value=old_value,
                new_value=new_value,
                reason="",
                source="user_edit",
                scene_id=None,
                status="applied",
                created_by=created_by,
                applied_by=created_by,
                applied_at=now,
            )
            _write_field(character, field, new_value)
            revisions.append(revision)
        await session.flush()
        return revisions

    async def record_ai_inferred(
        self,
        session: AsyncSession,
        *,
        character: Character,
        field: str,
        new_value: Any,
        reason: str,
        scene_id: str,
        created_by: str,
    ) -> CharacterRevision | None:
        """记录 AI 推演产出的状态变化：source='ai_inferred' status='pending'，
        需用户审核 apply 才会落到 characters 表。"""
        if field not in CHARACTER_REVISION_FIELDS:
            raise AppError(
                message=f"character_revision_field_not_allowed: {field}",
                code="validation_error",
            )
        old_value = _read_field(character, field)
        if old_value == new_value:
            return None
        await self._supersede_pending(
            session, character_id=character.id, field=field
        )
        repo = CharacterRevisionRepository(session)
        revision = await repo.create(
            organization_id=character.organization_id,
            project_id=character.project_id,
            character_id=character.id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            source="ai_inferred",
            scene_id=scene_id,
            status="pending",
            created_by=created_by,
            applied_by=None,
            applied_at=None,
        )
        await session.flush()
        return revision

    async def record_copilot_proposal(
        self,
        session: AsyncSession,
        *,
        character: Character,
        field: str,
        new_value: Any,
        reason: str,
        created_by: str,
    ) -> CharacterRevision | None:
        """记录 Copilot 提案：source='copilot' status='pending'。
        Revision Copilot apply_proposal 时调用 apply_revision() 将其落地。"""
        if field not in CHARACTER_REVISION_FIELDS:
            raise AppError(
                message=f"character_revision_field_not_allowed: {field}",
                code="validation_error",
            )
        old_value = _read_field(character, field)
        if old_value == new_value:
            return None
        await self._supersede_pending(
            session, character_id=character.id, field=field
        )
        repo = CharacterRevisionRepository(session)
        revision = await repo.create(
            organization_id=character.organization_id,
            project_id=character.project_id,
            character_id=character.id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            source="copilot",
            scene_id=None,
            status="pending",
            created_by=created_by,
            applied_by=None,
            applied_at=None,
        )
        await session.flush()
        return revision

    async def apply_revision(
        self,
        session: AsyncSession,
        *,
        revision_id: str,
        organization_id: str,
        applied_by: str,
    ) -> CharacterRevision:
        """应用一条 pending revision：写入 characters 表 + 标 applied。
        如果同字段已有 applied，标 superseded。"""
        rev_repo = CharacterRevisionRepository(session)
        revision = await rev_repo.get(revision_id, organization_id=organization_id)
        if not revision:
            raise NotFoundError("character_revision_not_found")
        if revision.status not in ("pending", "rejected"):
            raise AppError(
                message=f"character_revision_status_not_applicable: {revision.status}",
                code="validation_error",
            )
        character = await CharacterRepository(session).get(
            revision.character_id, organization_id=organization_id
        )
        if not character:
            raise NotFoundError("character_not_found")

        # 把同字段的旧 applied 标 superseded
        stmt = select(CharacterRevision).where(
            CharacterRevision.character_id == revision.character_id,
            CharacterRevision.field == revision.field,
            CharacterRevision.status == "applied",
            CharacterRevision.id != revision.id,
        )
        for old in (await session.execute(stmt)).scalars().all():
            old.status = "superseded"

        _write_field(character, revision.field, revision.new_value)
        revision.status = "applied"
        revision.applied_by = applied_by
        revision.applied_at = datetime.now(timezone.utc)
        await session.flush()
        return revision

    async def reject_revision(
        self,
        session: AsyncSession,
        *,
        revision_id: str,
        organization_id: str,
        actor_id: str,
    ) -> CharacterRevision:
        rev_repo = CharacterRevisionRepository(session)
        revision = await rev_repo.get(revision_id, organization_id=organization_id)
        if not revision:
            raise NotFoundError("character_revision_not_found")
        if revision.status != "pending":
            raise AppError(
                message=f"character_revision_status_not_pending: {revision.status}",
                code="validation_error",
            )
        revision.status = "rejected"
        revision.applied_by = actor_id
        revision.applied_at = datetime.now(timezone.utc)
        await session.flush()
        return revision

    async def rollback_to(
        self,
        session: AsyncSession,
        *,
        revision_id: str,
        organization_id: str,
        actor_id: str,
    ) -> CharacterRevision:
        """把一条历史 revision 重新 apply。
        实现方式：基于目标 revision 的 new_value 创建一条新的 source='user_edit' revision，
        当场 apply。这样回滚也在版本链里留痕，可追溯。"""
        rev_repo = CharacterRevisionRepository(session)
        target = await rev_repo.get(revision_id, organization_id=organization_id)
        if not target:
            raise NotFoundError("character_revision_not_found")
        character = await CharacterRepository(session).get(
            target.character_id, organization_id=organization_id
        )
        if not character:
            raise NotFoundError("character_not_found")
        # 当前字段值 → new_value
        current_value = _read_field(character, target.field)
        if current_value == target.new_value:
            # 目标 revision 已是当前值，无需回滚
            return target
        await self._supersede_pending(
            session, character_id=target.character_id, field=target.field
        )
        # 标记当前同字段 applied 为 superseded
        stmt = select(CharacterRevision).where(
            CharacterRevision.character_id == target.character_id,
            CharacterRevision.field == target.field,
            CharacterRevision.status == "applied",
        )
        for old in (await session.execute(stmt)).scalars().all():
            old.status = "superseded"
        now = datetime.now(timezone.utc)
        rollback_rev = await rev_repo.create(
            organization_id=character.organization_id,
            project_id=character.project_id,
            character_id=character.id,
            field=target.field,
            old_value=current_value,
            new_value=target.new_value,
            reason=f"回滚到 revision {target.id}",
            source="user_edit",
            scene_id=None,
            status="applied",
            created_by=actor_id,
            applied_by=actor_id,
            applied_at=now,
        )
        _write_field(character, target.field, target.new_value)
        await session.flush()
        return rollback_rev


character_tracker = CharacterTrackerService()
