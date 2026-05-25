"""认证服务。

封装 register / login / refresh / logout 业务逻辑。
refresh rotate 顺序保护：先发新对，确认成功后再撤销旧 jti。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt_tokens import create_access_token, create_refresh_token, decode_token
from app.core.passwords import hash_password, verify_password
from app.models.common import new_id
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.services.auth.token_store import is_refresh_jti_revoked, revoke_refresh_jti

BOOTSTRAP_SEED_EMAILS = {"writer@example.com"}


@dataclass
class TokenPair:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_jti: str
    refresh_expires_at: datetime
    user: User
    organization: Organization


class AuthService:
    async def register(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        display_name: str,
    ) -> TokenPair:
        email = email.strip().lower()
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="email_already_registered",
            )

        bootstrap_super_admin = await self._should_bootstrap_super_admin(session)
        user = User(
            id=new_id("user"),
            email=email,
            password_hash=hash_password(password),
            display_name=display_name or email.split("@")[0],
            status="active",
            is_platform_staff=bootstrap_super_admin,
            platform_role="super_admin" if bootstrap_super_admin else "user",
        )
        session.add(user)
        await session.flush()

        org = Organization(
            id=new_id("org"),
            name=f"{user.display_name} 的工作区",
            type="personal",
            owner_user_id=user.id,
            plan_code="Free",
            status="active",
        )
        session.add(org)
        await session.flush()

        session.add(
            OrganizationMember(
                id=new_id("mem"),
                organization_id=org.id,
                user_id=user.id,
                role="owner",
                status="active",
            )
        )
        await session.flush()
        return await self._issue_tokens(user, org)

    async def _should_bootstrap_super_admin(self, session: AsyncSession) -> bool:
        await self._acquire_bootstrap_lock(session)
        return not await self._has_real_user(session)

    async def _has_real_user(self, session: AsyncSession) -> bool:
        real_user = await session.execute(
            select(User.id)
            .where(User.email.not_in(BOOTSTRAP_SEED_EMAILS))
            .limit(1)
        )
        return real_user.scalar_one_or_none() is not None

    async def _has_real_super_admin(self, session: AsyncSession) -> bool:
        real_super_admin = await session.execute(
            select(User.id)
            .where(
                User.email.not_in(BOOTSTRAP_SEED_EMAILS),
                User.platform_role == "super_admin",
            )
            .limit(1)
        )
        return real_super_admin.scalar_one_or_none() is not None

    async def _acquire_bootstrap_lock(self, session: AsyncSession) -> None:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(2026051801)"))

    async def ensure_bootstrap_super_admin(self, session: AsyncSession) -> None:
        await self._acquire_bootstrap_lock(session)
        if await self._has_real_super_admin(session):
            return

        real_user = (
            await session.execute(
                select(User)
                .where(User.email.not_in(BOOTSTRAP_SEED_EMAILS))
                .order_by(User.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not real_user:
            return

        real_user.is_platform_staff = True
        real_user.platform_role = "super_admin"
        await session.commit()

    async def login(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
    ) -> TokenPair:
        email = email.strip().lower()
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_credentials",
            )
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user_inactive",
            )

        org = await self._resolve_default_org(session, user.id)
        return await self._issue_tokens(user, org)

    async def refresh(self, session: AsyncSession, refresh_token: str) -> TokenPair:
        """Rotate 流程：解析旧 → 校验黑名单 → 签新对 → 成功后撤销旧 jti。"""
        payload = decode_token(refresh_token, expected_type="refresh")
        old_jti = payload.get("jti")
        old_exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        if await is_refresh_jti_revoked(old_jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="refresh_token_revoked",
            )
        user = (
            await session.execute(select(User).where(User.id == payload.get("sub")))
        ).scalar_one_or_none()
        if not user or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="user_inactive",
            )

        org = await self._resolve_default_org(session, user.id)
        new_pair = await self._issue_tokens(user, org)
        # 仅在新对成功签发后才撤销旧 jti，避免用户中间态没有任何可用 token
        try:
            await revoke_refresh_jti(old_jti, old_exp)
        except Exception:  # noqa: BLE001 — Redis 失败不应阻断刷新
            pass
        return new_pair

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except HTTPException:
            return
        await revoke_refresh_jti(
            payload.get("jti"),
            datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )

    async def _resolve_default_org(self, session: AsyncSession, user_id: str) -> Organization:
        member = (
            await session.execute(
                select(OrganizationMember)
                .where(
                    OrganizationMember.user_id == user_id,
                    OrganizationMember.status == "active",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="no_organization",
            )
        org = (
            await session.execute(
                select(Organization).where(Organization.id == member.organization_id)
            )
        ).scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="organization_not_found",
            )
        return org

    async def _issue_tokens(self, user: User, org: Organization) -> TokenPair:
        access_token, access_exp = create_access_token(
            user_id=user.id,
            organization_id=org.id,
        )
        refresh_token, refresh_jti, refresh_exp = create_refresh_token(user_id=user.id)
        return TokenPair(
            access_token=access_token,
            access_expires_at=access_exp,
            refresh_token=refresh_token,
            refresh_jti=refresh_jti,
            refresh_expires_at=refresh_exp,
            user=user,
            organization=org,
        )


auth_service = AuthService()
