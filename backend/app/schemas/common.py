from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(APIModel):
    status: str
    service: str
    environment: str


class Timestamped(APIModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None
