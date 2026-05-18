from __future__ import annotations

from datetime import datetime
from typing import Any

from .common import APIModel


class PlanResponse(APIModel):
    code: str
    name: str
    description: str
    price_monthly: float
    status: str


class PlanFeatureResponse(APIModel):
    id: str
    plan_id: str
    feature_key: str
    enabled: bool
    limit_value: int | None = None
    limit_unit: str


class QuotaBalanceResponse(APIModel):
    id: str
    organization_id: str
    quota_key: str
    limit_value: int
    used_value: int
    reserved_value: int
    period_start: datetime
    period_end: datetime
    reset_at: datetime


class UsageEventResponse(APIModel):
    id: str
    organization_id: str
    user_id: str
    project_id: str | None = None
    job_id: str | None = None
    event_type: str
    amount: int
    unit: str
    event_metadata: dict[str, Any] | None = None
    created_at: datetime
