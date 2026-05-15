from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class Character(Base, TenantMixin, TimestampMixin):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    role: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    secret: Mapped[str] = mapped_column(Text, default="")
    arc: Mapped[str] = mapped_column(Text, default="")
    relationships: Mapped[dict] = mapped_column(JSON, default=dict)
    current_state: Mapped[dict] = mapped_column(JSON, default=dict)
