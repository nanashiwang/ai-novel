from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class UsageEvent(Base, TenantMixin, TimestampMixin):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    amount: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(32))
    event_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
