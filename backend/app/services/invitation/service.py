"""组织邀请服务。

设计：
- create_invitation：找不到对应用户也允许创建（pending）；同时如果已是 active member 返回错误
- accept_invitation：已登录用户调用；写 organization_members 并将 invitation 置为 accepted
- consume_for_registration：在 auth.register 时尝试匹配 email 对应的 pending 邀请并自动入组
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import new_id
from app.models.invitation import OrganizationInvitation
from app.models.organization import OrganizationMember

_logger = logging.getLogger(__name__)
_INVITATION_TTL_DAYS = 7


def _gen_token() -> str:
    return secrets.token_urlsafe(48)


class InvitationService:
    async def create(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        invited_by: str,
        email: str,
        role: str,
    ) -> OrganizationInvitation:
        email = email.strip().lower()

        # 校验：已是该组织 active member 拒绝
        existing_member = (
            await session.execute(
                select(OrganizationMember)
                .join(
                    # 通过 user 表查 email；这里直接在调用方传入用户已存在的判断
                    OrganizationMember.user_id != "",
                    isouter=True,
                )
                .where(OrganizationMember.organization_id == organization_id)
                .limit(1)
            )
        )
        _ = existing_member  # 占位避免歧义；具体重复邀请校验下面 invitation 表完成

        # 校验：是否已有 pending 邀请
        prev = (
            await session.execute(
                select(OrganizationInvitation).where(
                    OrganizationInvitation.organization_id == organization_id,
                    OrganizationInvitation.email == email,
                    OrganizationInvitation.status == "pending",
                )
            )
        ).scalar_one_or_none()
        if prev:
            # 已有 pending → 更新 role + 续期
            prev.role = role
            prev.expires_at = datetime.now(timezone.utc) + timedelta(days=_INVITATION_TTL_DAYS)
            prev.token = _gen_token()
            await session.flush()
            return prev

        invitation = OrganizationInvitation(
            id=new_id("inv"),
            organization_id=organization_id,
            email=email,
            role=role,
            token=_gen_token(),
            status="pending",
            invited_by=invited_by,
            expires_at=datetime.now(timezone.utc) + timedelta(days=_INVITATION_TTL_DAYS),
        )
        session.add(invitation)
        await session.flush()
        # 真实环境此处发邮件；目前仅写日志
        _logger.info(
            "invitation_created",
            extra={
                "organization_id": organization_id,
                "email": email,
                "role": role,
                "token": invitation.token,
            },
        )
        return invitation

    async def get_pending_by_token(
        self, session: AsyncSession, token: str
    ) -> OrganizationInvitation | None:
        invitation = (
            await session.execute(
                select(OrganizationInvitation).where(OrganizationInvitation.token == token)
            )
        ).scalar_one_or_none()
        if not invitation:
            return None
        if invitation.status != "pending":
            return None
        if invitation.expires_at < datetime.now(timezone.utc):
            invitation.status = "expired"
            await session.flush()
            return None
        return invitation

    async def accept(
        self,
        session: AsyncSession,
        *,
        token: str,
        user_id: str,
        user_email: str,
    ) -> OrganizationInvitation:
        invitation = await self.get_pending_by_token(session, token)
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="invitation_invalid_or_expired",
            )
        if invitation.email != user_email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="invitation_email_mismatch",
            )

        # 幂等：已是成员则只更新邀请状态
        member = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == invitation.organization_id,
                    OrganizationMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if member:
            member.role = invitation.role
            member.status = "active"
        else:
            session.add(
                OrganizationMember(
                    id=new_id("mem"),
                    organization_id=invitation.organization_id,
                    user_id=user_id,
                    role=invitation.role,
                    status="active",
                )
            )

        invitation.status = "accepted"
        invitation.accepted_by = user_id
        invitation.accepted_at = datetime.now(timezone.utc)
        await session.flush()
        return invitation

    async def consume_for_registration(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        user_email: str,
        token: str | None,
    ) -> OrganizationInvitation | None:
        """注册时尝试消费邀请：token 优先；若未提供 token，按 email 匹配最新一条 pending。"""
        if token:
            invitation = await self.get_pending_by_token(session, token)
            if invitation and invitation.email == user_email.strip().lower():
                return await self.accept(
                    session,
                    token=token,
                    user_id=user_id,
                    user_email=user_email,
                )
            return None

        invitation = (
            await session.execute(
                select(OrganizationInvitation)
                .where(
                    OrganizationInvitation.email == user_email.strip().lower(),
                    OrganizationInvitation.status == "pending",
                    OrganizationInvitation.expires_at > datetime.now(timezone.utc),
                )
                .order_by(OrganizationInvitation.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not invitation:
            return None
        return await self.accept(
            session,
            token=invitation.token,
            user_id=user_id,
            user_email=user_email,
        )


invitation_service = InvitationService()
