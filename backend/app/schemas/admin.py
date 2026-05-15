from .common import APIModel


class AuditLogResponse(APIModel):
    id: str
    actor_user_id: str
    organization_id: str
    action: str
    target_type: str
    target_id: str


class AdminQuotaAdjustRequest(APIModel):
    organization_id: str
    quota_key: str
    amount: int
    reason: str
