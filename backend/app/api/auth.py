from fastapi import APIRouter

from app.api.deps import CurrentUserDep, TenantDep
from app.schemas.auth import CurrentUserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUserDep, tenant: TenantDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        platform_role=user.platform_role,
        organization_role=user.organization_role,
        organization_id=tenant.organization_id,
        organization_name=tenant.organization_name,
        plan_code=tenant.plan_code,
    )


@router.post("/login")
async def login() -> dict:
    return {"status": "mock_login", "message": "真实登录将在后续阶段接入"}


@router.post("/register")
async def register() -> dict:
    return {"status": "mock_register", "message": "真实注册将在后续阶段接入"}
