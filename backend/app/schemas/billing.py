from .common import APIModel


class PlanResponse(APIModel):
    code: str
    name: str
    description: str
    price_monthly: float
    status: str


class QuotaBalanceResponse(APIModel):
    organization_id: str
    quota_key: str
    limit_value: int
    used_value: int
    reserved_value: int
    reset_at: str


class UsageEventResponse(APIModel):
    id: str
    organization_id: str
    event_type: str
    amount: int
    unit: str
