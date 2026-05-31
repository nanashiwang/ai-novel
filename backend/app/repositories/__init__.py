"""集中导出的 Repository 工厂。

将所有资源 repository 聚合到此模块，service 层通过
`from app.repositories import UserRepository` 即可使用，避免分散导入。
"""
from __future__ import annotations

from sqlalchemy import delete, select

from app.models.audit_log import AdminAuditLog
from app.models.chapter import Chapter, Volume
from app.models.chapter_state_requirement import ChapterStateRequirement
from app.models.character import Character
from app.models.character_revision import CharacterRevision
from app.models.continuity_issue import ContinuityIssue
from app.models.draft_version import DraftVersion
from app.models.export_file import ExportFile
from app.models.generation_job import GenerationJob
from app.models.information_ledger import InformationLedger
from app.models.invitation import OrganizationInvitation
from app.models.memory import MemoryEntry
from app.models.model_call import ModelCall
from app.models.organization import Organization, OrganizationMember
from app.models.plan import Plan, PlanFeature
from app.models.plot_thread import PlotThread
from app.models.plot_thread_revision import PlotThreadRevision
from app.models.project import NovelSpec, Project
from app.models.prompt_experiment import PromptExperiment
from app.models.quota import QuotaBalance, QuotaReservation
from app.models.revision import (
    RevisionAppliedChange,
    RevisionMessage,
    RevisionProposal,
    RevisionSession,
)
from app.models.scene import Scene
from app.models.story_state_history import StoryStateHistory
from app.models.story_state_item import StoryStateItem
from app.models.story_state_maintenance_action import StoryStateMaintenanceAction
from app.models.style_sample import StyleSample
from app.models.system_setting import SystemSetting
from app.models.usage import UsageEvent
from app.models.user import User
from app.models.world_item import WorldItem
from app.models.world_item_revision import WorldItemRevision
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User
    id_prefix = "user"


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization
    id_prefix = "org"


class OrganizationMemberRepository(BaseRepository[OrganizationMember]):
    model = OrganizationMember
    id_prefix = "mem"


class OrganizationInvitationRepository(BaseRepository[OrganizationInvitation]):
    model = OrganizationInvitation
    id_prefix = "inv"


class PlanRepository(BaseRepository[Plan]):
    model = Plan
    id_prefix = "plan"


class PlanFeatureRepository(BaseRepository[PlanFeature]):
    model = PlanFeature
    id_prefix = "pf"


class ProjectRepository(BaseRepository[Project]):
    model = Project
    id_prefix = "project"


class PlotThreadRepository(BaseRepository[PlotThread]):
    model = PlotThread
    id_prefix = "thread"


class NovelSpecRepository(BaseRepository[NovelSpec]):
    model = NovelSpec
    id_prefix = "spec"


class VolumeRepository(BaseRepository[Volume]):
    model = Volume
    id_prefix = "volume"


class ChapterRepository(BaseRepository[Chapter]):
    model = Chapter
    id_prefix = "chapter"


class SceneRepository(BaseRepository[Scene]):
    model = Scene
    id_prefix = "scene"


class CharacterRepository(BaseRepository[Character]):
    model = Character
    id_prefix = "char"


class CharacterRevisionRepository(BaseRepository[CharacterRevision]):
    model = CharacterRevision
    id_prefix = "char_rev"


class WorldItemRepository(BaseRepository[WorldItem]):
    model = WorldItem
    id_prefix = "world"


class WorldItemRevisionRepository(BaseRepository[WorldItemRevision]):
    model = WorldItemRevision
    id_prefix = "wir"


class PlotThreadRevisionRepository(BaseRepository[PlotThreadRevision]):
    model = PlotThreadRevision
    id_prefix = "ptr"


class PromptExperimentRepository(BaseRepository[PromptExperiment]):
    model = PromptExperiment
    id_prefix = "pexp"


class MemoryRepository(BaseRepository[MemoryEntry]):
    model = MemoryEntry
    id_prefix = "mem_entry"


class StyleSampleRepository(BaseRepository[StyleSample]):
    model = StyleSample
    id_prefix = "style"


class StoryStateRepository(BaseRepository[StoryStateItem]):
    model = StoryStateItem
    id_prefix = "state"

    async def get_by_identity(
        self,
        *,
        organization_id: str,
        project_id: str,
        entity_type: str,
        entity_id: str | None,
        state_type: str,
        name: str,
    ) -> StoryStateItem | None:
        stmt = select(StoryStateItem).where(
            StoryStateItem.organization_id == organization_id,
            StoryStateItem.project_id == project_id,
            StoryStateItem.entity_type == entity_type,
            StoryStateItem.state_type == state_type,
            StoryStateItem.name == name,
        )
        if entity_id:
            stmt = stmt.where(StoryStateItem.entity_id == entity_id)
        else:
            stmt = stmt.where(StoryStateItem.entity_id.is_(None))
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        *,
        organization_id: str,
        project_id: str,
        state_type: str | None = None,
        status: str | None = None,
        entity_type: str | None = None,
        hard_only: bool = False,
        limit: int = 100,
    ):
        stmt = select(StoryStateItem).where(
            StoryStateItem.organization_id == organization_id,
            StoryStateItem.project_id == project_id,
        )
        if state_type:
            stmt = stmt.where(StoryStateItem.state_type == state_type)
        if status:
            stmt = stmt.where(StoryStateItem.status == status)
        if entity_type:
            stmt = stmt.where(StoryStateItem.entity_type == entity_type)
        if hard_only:
            stmt = stmt.where(StoryStateItem.is_hard_constraint.is_(True))
        stmt = stmt.order_by(
            StoryStateItem.is_hard_constraint.desc(),
            StoryStateItem.priority.desc(),
            StoryStateItem.updated_at.desc(),
        ).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class StoryStateHistoryRepository(BaseRepository[StoryStateHistory]):
    model = StoryStateHistory
    id_prefix = "state_history"

    async def list_for_state(
        self,
        *,
        organization_id: str,
        project_id: str,
        state_item_id: str,
    ):
        stmt = (
            select(StoryStateHistory)
            .where(
                StoryStateHistory.organization_id == organization_id,
                StoryStateHistory.project_id == project_id,
                StoryStateHistory.state_item_id == state_item_id,
            )
            .order_by(StoryStateHistory.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class StoryStateMaintenanceActionRepository(BaseRepository[StoryStateMaintenanceAction]):
    model = StoryStateMaintenanceAction
    id_prefix = "state_action"

    async def list_for_project(
        self,
        *,
        organization_id: str,
        project_id: str,
        status: str | None = None,
        limit: int = 100,
    ):
        stmt = select(StoryStateMaintenanceAction).where(
            StoryStateMaintenanceAction.organization_id == organization_id,
            StoryStateMaintenanceAction.project_id == project_id,
        )
        if status:
            stmt = stmt.where(StoryStateMaintenanceAction.status == status)
        stmt = stmt.order_by(StoryStateMaintenanceAction.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class ChapterStateRequirementRepository(BaseRepository[ChapterStateRequirement]):
    model = ChapterStateRequirement
    id_prefix = "state_req"

    async def list_for_chapter(
        self,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
        status: str | None = None,
        order_by=None,
    ):
        stmt = select(ChapterStateRequirement).where(
            ChapterStateRequirement.organization_id == organization_id,
            ChapterStateRequirement.project_id == project_id,
            ChapterStateRequirement.chapter_id == chapter_id,
        )
        if status:
            stmt = stmt.where(ChapterStateRequirement.status == status)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        else:
            stmt = stmt.order_by(ChapterStateRequirement.priority.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_for_chapter(
        self,
        *,
        organization_id: str,
        project_id: str,
        chapter_id: str,
    ) -> int:
        stmt = delete(ChapterStateRequirement).where(
            ChapterStateRequirement.organization_id == organization_id,
            ChapterStateRequirement.project_id == project_id,
            ChapterStateRequirement.chapter_id == chapter_id,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)


class GenerationJobRepository(BaseRepository[GenerationJob]):
    model = GenerationJob
    id_prefix = "job"


class InformationLedgerRepository(BaseRepository[InformationLedger]):
    model = InformationLedger
    id_prefix = "ledger"


class ModelCallRepository(BaseRepository[ModelCall]):
    model = ModelCall
    id_prefix = "model_call"


class UsageEventRepository(BaseRepository[UsageEvent]):
    model = UsageEvent
    id_prefix = "usage"


class ContinuityIssueRepository(BaseRepository[ContinuityIssue]):
    model = ContinuityIssue
    id_prefix = "issue"


class DraftVersionRepository(BaseRepository[DraftVersion]):
    model = DraftVersion
    id_prefix = "draft"


class ExportFileRepository(BaseRepository[ExportFile]):
    model = ExportFile
    id_prefix = "export"


class AuditLogRepository(BaseRepository[AdminAuditLog]):
    model = AdminAuditLog
    id_prefix = "audit"


class SystemSettingRepository(BaseRepository[SystemSetting]):
    model = SystemSetting
    id_prefix = "setting"


class RevisionSessionRepository(BaseRepository[RevisionSession]):
    model = RevisionSession
    id_prefix = "rev_session"


class RevisionMessageRepository(BaseRepository[RevisionMessage]):
    model = RevisionMessage
    id_prefix = "rev_msg"


class RevisionProposalRepository(BaseRepository[RevisionProposal]):
    model = RevisionProposal
    id_prefix = "rev_prop"


class RevisionAppliedChangeRepository(BaseRepository[RevisionAppliedChange]):
    model = RevisionAppliedChange
    id_prefix = "rev_change"


class QuotaBalanceRepository(BaseRepository[QuotaBalance]):
    """额度余额仓储，包含针对竞态的行级锁查询。"""

    model = QuotaBalance
    id_prefix = "quota"

    async def get_for_update(
        self,
        *,
        organization_id: str,
        quota_key: str,
    ) -> QuotaBalance | None:
        """在事务内对额度行加 SELECT ... FOR UPDATE 锁。"""
        stmt = (
            select(QuotaBalance)
            .where(
                QuotaBalance.organization_id == organization_id,
                QuotaBalance.quota_key == quota_key,
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class QuotaReservationRepository(BaseRepository[QuotaReservation]):
    model = QuotaReservation
    id_prefix = "reservation"


__all__ = [
    "AuditLogRepository",
    "ChapterRepository",
    "CharacterRepository",
    "CharacterRevisionRepository",
    "ChapterStateRequirementRepository",
    "ContinuityIssueRepository",
    "DraftVersionRepository",
    "ExportFileRepository",
    "GenerationJobRepository",
    "InformationLedgerRepository",
    "MemoryRepository",
    "ModelCallRepository",
    "NovelSpecRepository",
    "OrganizationInvitationRepository",
    "OrganizationMemberRepository",
    "OrganizationRepository",
    "PlanFeatureRepository",
    "PlanRepository",
    "PlotThreadRepository",
    "PlotThreadRevisionRepository",
    "ProjectRepository",
    "PromptExperimentRepository",
    "QuotaBalanceRepository",
    "QuotaReservationRepository",
    "RevisionSessionRepository",
    "RevisionProposalRepository",
    "RevisionMessageRepository",
    "RevisionAppliedChangeRepository",
    "SceneRepository",
    "StyleSampleRepository",
    "StoryStateHistoryRepository",
    "StoryStateMaintenanceActionRepository",
    "StoryStateRepository",
    "SystemSettingRepository",
    "UsageEventRepository",
    "UserRepository",
    "VolumeRepository",
    "WorldItemRepository",
    "WorldItemRevisionRepository",
]
