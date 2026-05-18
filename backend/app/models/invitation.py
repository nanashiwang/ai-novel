from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .common import TenantMixin, TimestampMixin


class OrganizationInvitation(Base, TenantMixin, TimestampMixin):
    """组织邀请。

    - 已注册用户：接受后写 organization_members
    - 未注册用户：随邀请 token 注册，注册流程自动绑定
    """

    __tablename__ = "organization_invitations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(64), default="editor")
    token: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    invited_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
