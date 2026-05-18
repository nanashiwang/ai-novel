"""Auth API。

提供真实的 register / login / refresh / logout / me 端点。
refresh_token 通过 httpOnly cookie 下发；access_token 在 body 返回。
登录与注册端点接限流。
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth.service import TokenPair, auth_service
from app.services.invitation.service import invitation_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _set_refresh_cookie(response: Response, token_pair: TokenPair) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token_pair.refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path="/")


def _to_user_response(token_pair: TokenPair) -> CurrentUserResponse:
    # 个人注册时默认是 owner；admin seed 也是 owner
    return CurrentUserResponse(
        id=token_pair.user.id,
        email=token_pair.user.email,
        display_name=token_pair.user.display_name,
        platform_role=token_pair.user.platform_role,
        organization_role="owner",
        organization_id=token_pair.organization.id,
        organization_name=token_pair.organization.name,
        plan_code=token_pair.organization.plan_code,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_register)
async def register(
    request: Request, payload: RegisterRequest, response: Response, db: DbDep
) -> TokenResponse:
    token_pair = await auth_service.register(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name or "",
    )
    # 尝试消费邀请：邀请失败不能影响注册事务。
    try:
        async with db.begin_nested():
            await invitation_service.consume_for_registration(
                db,
                user_id=token_pair.user.id,
                user_email=token_pair.user.email,
                token=payload.invitation_token,
            )
    except Exception:  # noqa: BLE001 — 邀请处理失败不阻断注册
        pass
    await db.commit()
    _set_refresh_cookie(response, token_pair)
    return TokenResponse(
        access_token=token_pair.access_token,
        expires_at=token_pair.access_expires_at,
        user=_to_user_response(token_pair),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_login)
async def login(
    request: Request, payload: LoginRequest, response: Response, db: DbDep
) -> TokenResponse:
    token_pair = await auth_service.login(
        db,
        email=payload.email,
        password=payload.password,
    )
    _set_refresh_cookie(response, token_pair)
    return TokenResponse(
        access_token=token_pair.access_token,
        expires_at=token_pair.access_expires_at,
        user=_to_user_response(token_pair),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: DbDep,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="missing_refresh_token")
    token_pair = await auth_service.refresh(db, refresh_token)
    _set_refresh_cookie(response, token_pair)
    return TokenResponse(
        access_token=token_pair.access_token,
        expires_at=token_pair.access_expires_at,
        user=_to_user_response(token_pair),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
) -> Response:
    await auth_service.logout(refresh_token)
    _clear_refresh_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUserDep, tenant: TenantDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        platform_role=user.platform_role,
        organization_role=tenant.organization_role,
        organization_id=tenant.organization_id,
        organization_name=tenant.organization_name,
        plan_code=tenant.plan_code,
    )
