"""风格样本 API schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class StyleSampleCreate(APIModel):
    label: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=10000)


class StyleSampleResponse(APIModel):
    id: str
    organization_id: str
    project_id: str
    label: str
    content: str
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = ["StyleSampleCreate", "StyleSampleResponse"]
