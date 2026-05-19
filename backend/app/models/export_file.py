from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class ExportFile(Base, TenantMixin, TimestampMixin):
    __tablename__ = "export_files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), index=True)
    export_type: Mapped[str] = mapped_column(String(64))
    # Sprint 5-B：file_url 指向 download endpoint，Sprint 6 接 MinIO 时可
    # 改为预签名 URL；前端只读 file_url 不感知后端 storage。
    file_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(64), default="queued")
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    # 同步导出阶段直接把文件内容存 db，避免引入 MinIO 依赖。整本中文小说
    # ~ 200k 字 ≈ 600KB，Postgres TEXT 上限 1GB 够用；后续 Sprint 6 迁出。
    content: Mapped[str] = mapped_column(Text, default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
