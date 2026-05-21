"""信息释放 ledger 的 API schemas（Sprint 14-C5）。"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel

# 三态机：
# - secret：完全未公开
# - partial：暗示性透露（例如旁敲侧击）
# - public：所有相关角色已知
LedgerStatus = Literal["secret", "partial", "public"]


class LedgerCreate(APIModel):
    fact: str = Field(min_length=1, max_length=2000)
    owners: list[str] = Field(default_factory=list)
    disclosed_to: list[str] = Field(default_factory=list)
    first_revealed_scene_id: str | None = None
    planned_reveal_chapter: int | None = Field(default=None, ge=1)
    status: LedgerStatus = "secret"
    importance: int = Field(default=3, ge=1, le=5)


class LedgerUpdate(APIModel):
    fact: str | None = Field(default=None, max_length=2000)
    owners: list[str] | None = None
    disclosed_to: list[str] | None = None
    first_revealed_scene_id: str | None = None
    planned_reveal_chapter: int | None = Field(default=None, ge=1)
    status: LedgerStatus | None = None
    importance: int | None = Field(default=None, ge=1, le=5)


class LedgerStatusUpdate(APIModel):
    status: LedgerStatus


class LedgerResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    fact: str
    owners: list[str] = []
    disclosed_to: list[str] = []
    first_revealed_scene_id: str | None = None
    planned_reveal_chapter: int | None = None
    status: LedgerStatus
    importance: int

