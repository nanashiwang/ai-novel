from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class QuotaBalance(Base, TenantMixin, TimestampMixin):
    __tablename__ = "quota_balances"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quota_key: Mapped[str] = mapped_column(String(120), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    limit_value: Mapped[int] = mapped_column(Integer)
    used_value: Mapped[int] = mapped_column(Integer, default=0)
    reserved_value: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuotaReservation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "quota_reservations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("generation_jobs.id"), index=True)
    quota_key: Mapped[str] = mapped_column(String(120), index=True)
    reserved_amount: Mapped[int] = mapped_column(Integer)
    consumed_amount: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="reserved")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
