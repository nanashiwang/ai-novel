from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class RevisionSession(Base, TenantMixin, TimestampMixin):
    __tablename__ = "revision_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    scope: Mapped[str] = mapped_column(String(64), default="story_bible")
    title: Mapped[str] = mapped_column(String(200), default="AI 设定共创")
    status: Mapped[str] = mapped_column(String(32), default="active")


class RevisionMessage(Base, TenantMixin, TimestampMixin):
    __tablename__ = "revision_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("revision_sessions.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text, default="")


class RevisionProposal(Base, TenantMixin, TimestampMixin):
    __tablename__ = "revision_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("revision_sessions.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32), default="update")
    title: Mapped[str] = mapped_column(String(200), default="设定优化提案")
    reason: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[list[str]] = mapped_column(JSON, default=list)
    patch: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")


class RevisionAppliedChange(Base, TenantMixin, TimestampMixin):
    __tablename__ = "revision_applied_changes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("revision_sessions.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("revision_proposals.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_data: Mapped[dict] = mapped_column(JSON, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, default=dict)
    applied_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
