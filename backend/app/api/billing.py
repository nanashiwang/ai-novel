from fastapi import APIRouter
from app.schemas.billing import PlanResponse
from app.services.billing.service import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanResponse])
async def plans() -> list[dict]:
    return billing_service.list_plans()


@router.post("/checkout-session")
async def checkout_session() -> dict:
    return {"status": "mock", "message": "支付网关后续接入"}
