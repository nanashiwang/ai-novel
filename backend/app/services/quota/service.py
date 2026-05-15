from __future__ import annotations

from fastapi import HTTPException, status

from app.core.tenancy import TenantContext
from app.repositories.memory_store import insert_row, list_rows, update_row


class QuotaService:
    def list_balances(self, tenant: TenantContext) -> list[dict]:
        return list_rows("quota_balances", tenant.organization_id)

    def reserve_quota(
        self,
        tenant: TenantContext,
        job_id: str,
        quota_key: str,
        amount: int,
    ) -> dict:
        balances = self.list_balances(tenant)
        balance = next((item for item in balances if item["quota_key"] == quota_key), None)
        if not balance:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="quota_not_configured",
            )
        available = balance["limit_value"] - balance["used_value"] - balance["reserved_value"]
        if available < amount:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="quota_insufficient",
            )
        new_reserved = balance["reserved_value"] + amount
        for raw in list_rows("quota_balances", tenant.organization_id):
            if raw["quota_key"] == quota_key:
                update_row(
                    "quota_balances",
                    raw["id"],
                    {"reserved_value": new_reserved},
                    tenant.organization_id,
                )
        return insert_row(
            "quota_reservations",
            {
                "organization_id": tenant.organization_id,
                "job_id": job_id,
                "quota_key": quota_key,
                "reserved_amount": amount,
                "consumed_amount": 0,
                "status": "reserved",
            },
            "reservation",
        )

    def record_usage(
        self,
        tenant: TenantContext,
        user_id: str,
        event_type: str,
        amount: int,
        unit: str,
        project_id: str | None = None,
        job_id: str | None = None,
    ) -> dict:
        return insert_row(
            "usage_events",
            {
                "organization_id": tenant.organization_id,
                "user_id": user_id,
                "project_id": project_id,
                "job_id": job_id,
                "event_type": event_type,
                "amount": amount,
                "unit": unit,
            },
            "usage",
        )


quota_service = QuotaService()
