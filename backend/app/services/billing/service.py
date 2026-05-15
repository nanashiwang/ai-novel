from app.repositories.memory_store import list_rows


class BillingService:
    def list_plans(self) -> list[dict]:
        return list_rows("plans")


billing_service = BillingService()
