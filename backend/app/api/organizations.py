"""组织 API。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import EmailStr, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.models.organization import Organization, OrganizationMember
from app.repositories import (
    OrganizationMemberRepository,
    OrganizationRepository,
    UserRepository,
)
from app.schemas.common import APIModel
from app.services.invitation.service import invitation_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationResponse(APIModel):
    id: str
    name: str
    type: str
    plan_code: str
    status: str
    owner_user_id: str


class OrganizationUpdate(APIModel):
    name: str | None = None
    plan_code: str | None = None
    status: str | None = None


class MemberResponse(APIModel):
    id: str
    organization_id: str
    user_id: str
    role: str
    status: str


class InviteMemberPayload(APIModel):
    email: EmailStr
    role: str = Field(default="editor", pattern=r"^(owner|editor|viewer|billing_manager)$")


class InvitationResponse(APIModel):
    id: str
    organization_id: str
    email: str
    role: str
    token: str
    status: str
    expires_at: str


class AcceptInvitationPayload(APIModel):
    token: str


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(user: CurrentUserDep, db: DbDep):
    """返回当前用户所属的全部组织。"""
    stmt = (
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.status == "active",
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.get("/current", response_model=OrganizationResponse)
async def get_current_org(tenant: TenantDep, db: DbDep):
    org = await OrganizationRepository(db).get(tenant.organization_id)
    if not org:
        raise NotFoundError("organization_not_found")
    return org


@router.patch("/current", response_model=OrganizationResponse)
async def update_current_org(
    payload: OrganizationUpdate,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "organization:manage", tenant)
    org = await OrganizationRepository(db).update(
        tenant.organization_id,
        {k: v for k, v in payload.model_dump().items() if v is not None},
    )
    if not org:
        raise NotFoundError("organization_not_found")
    await db.commit()
    return org


@router.get("/current/members", response_model=list[MemberResponse])
async def list_members(tenant: TenantDep, db: DbDep):
    rows = await OrganizationMemberRepository(db).list(organization_id=tenant.organization_id)
    return rows


@router.post(
    "/current/members",
    response_model=MemberResponse | InvitationResponse,
    status_code=201,
)
async def invite_member(
    payload: InviteMemberPayload,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
) -> MemberResponse | InvitationResponse:
    """邀请成员：

    - 邮箱对应用户已注册：直接写 organization_members → 返回 MemberResponse
    - 未注册：创建 pending invitation → 返回 InvitationResponse（含 token，前端用于生成邮件链接）
    """
    require_permission(user, "organization:manage", tenant)
    user_repo = UserRepository(db)
    target = await user_repo.get_by(email=str(payload.email).lower())

    if target:
        member_repo = OrganizationMemberRepository(db)
        existing = (
            await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == tenant.organization_id,
                    OrganizationMember.user_id == target.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.role = payload.role
            existing.status = "active"
            await db.commit()
            return existing  # type: ignore[return-value]
        member = await member_repo.create(
            organization_id=tenant.organization_id,
            user_id=target.id,
            role=payload.role,
            status="active",
        )
        await db.commit()
        return member  # type: ignore[return-value]

    # 未注册：创建邀请
    invitation = await invitation_service.create(
        db,
        organization_id=tenant.organization_id,
        invited_by=user.id,
        email=str(payload.email),
        role=payload.role,
    )
    await db.commit()
    return InvitationResponse(
        id=invitation.id,
        organization_id=invitation.organization_id,
        email=invitation.email,
        role=invitation.role,
        token=invitation.token,
        status=invitation.status,
        expires_at=invitation.expires_at.isoformat(),
    )


@router.delete("/current/members/{member_id}", status_code=204)
async def remove_member(
    member_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "organization:manage", tenant)
    repo = OrganizationMemberRepository(db)
    member = await repo.get(member_id, organization_id=tenant.organization_id)
    if not member:
        raise NotFoundError("member_not_found")
    await repo.delete(member_id, organization_id=tenant.organization_id)
    await db.commit()


@router.post("/invitations/accept", response_model=MemberResponse, status_code=200)
async def accept_invitation(
    payload: AcceptInvitationPayload,
    user: CurrentUserDep,
    db: DbDep,
):
    """已登录用户接受邀请。"""
    await invitation_service.accept(
        db,
        token=payload.token,
        user_id=user.id,
        user_email=user.email,
    )
    await db.commit()
    member = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.status == "active",
            ).order_by(OrganizationMember.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not member:
        raise NotFoundError("member_not_found")
    return member
