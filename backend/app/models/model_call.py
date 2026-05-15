from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class ModelCall(Base, TenantMixin, TimestampMixin):
    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("projects.id"),
        index=True,
    )
    job_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("generation_jobs.id"),
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(120), index=True)
    model: Mapped[str] = mapped_column(String(120))
    prompt_key: Mapped[str] = mapped_column(String(160), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="v1")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    user_prompt: Mapped[str] = mapped_column(Text, default="")
    response_text: Mapped[Optional[str]] = mapped_column(Text)
    response_json: Mapped[Optional[dict]] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    status: Mapped[str] = mapped_column(String(32), default="success")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
