"""集中导出的 Repository 工厂。

将所有资源 repository 聚合到此模块，service 层通过
`from app.repositories import UserRepository` 即可使用，避免分散导入。
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.audit_log import AdminAuditLog
from app.models.chapter import Chapter, Volume
from app.models.character import Character
from app.models.character_revision import CharacterRevision
from app.models.continuity_issue import ContinuityIssue
from app.models.draft_version import DraftVersion
from app.models.export_file import ExportFile
from app.models.generation_job import GenerationJob
from app.models.invitation import OrganizationInvitation
from app.models.memory import MemoryEntry
from app.models.model_call import ModelCall
from app.models.organization import Organization, OrganizationMember
from app.models.plan import Plan, PlanFeature
from app.models.plot_thread import PlotThread
from app.models.project import NovelSpec, Project
from app.models.quota import QuotaBalance, QuotaReservation
from app.models.revision import (
    RevisionAppliedChange,
    RevisionMessage,
    RevisionProposal,
    RevisionSession,
)
from app.models.scene import Scene
from app.models.system_setting import SystemSetting
from app.models.usage import UsageEvent
from app.models.user import User
from app.models.world_item import WorldItem
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


class MemoryRepository(BaseRepository[MemoryEntry]):
    model = MemoryEntry
    id_prefix = "mem_entry"


class GenerationJobRepository(BaseRepository[GenerationJob]):
    model = GenerationJob
    id_prefix = "job"


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
    "ContinuityIssueRepository",
    "DraftVersionRepository",
    "ExportFileRepository",
    "GenerationJobRepository",
    "MemoryRepository",
    "ModelCallRepository",
    "NovelSpecRepository",
    "OrganizationInvitationRepository",
    "OrganizationMemberRepository",
    "OrganizationRepository",
    "PlanFeatureRepository",
    "PlanRepository",
    "PlotThreadRepository",
    "ProjectRepository",
    "QuotaBalanceRepository",
    "QuotaReservationRepository",
    "RevisionSessionRepository",
    "RevisionProposalRepository",
    "RevisionMessageRepository",
    "RevisionAppliedChangeRepository",
    "SceneRepository",
    "SystemSettingRepository",
    "UsageEventRepository",
    "UserRepository",
    "VolumeRepository",
    "WorldItemRepository",
]
