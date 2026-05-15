from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class WorldItem(Base, TenantMixin, TimestampMixin):
    __tablename__ = "world_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    related_characters: Mapped[list[str]] = mapped_column(JSON, default=list)
    importance: Mapped[str] = mapped_column(String(32), default="medium")
    is_hard_rule: Mapped[bool] = mapped_column(default=False)
