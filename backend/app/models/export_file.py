from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from .common import TenantMixin, TimestampMixin


class ExportFile(Base, TenantMixin, TimestampMixin):
    __tablename__ = "export_files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    export_type: Mapped[str] = mapped_column(String(64))
    file_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(64), default="queued")
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
