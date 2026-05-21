"""风格样本 API（Sprint 14-C4）。

用户为项目上传若干段示例文字，作为后续 scene 写作时的风格参考。
创建时后端会同步调用 embedding_service.embed 把文本变成向量存进 DB；
ContextBuilder 在写场景时按当前 scene 召回 top-K 段最相近的样本。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, TenantDep
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.repositories import StyleSampleRepository
from app.schemas.style_sample import StyleSampleCreate, StyleSampleResponse
from app.services.embedding import embedding_service

router = APIRouter(prefix="/projects/{project_id}/style-samples", tags=["style-samples"])


@router.get("", response_model=list[StyleSampleResponse])
async def list_style_samples(
    project_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:read", tenant)
    rows = await StyleSampleRepository(db).list(
        organization_id=tenant.organization_id,
        project_id=project_id,
    )
    return rows


@router.post("", response_model=StyleSampleResponse, status_code=201)
async def create_style_sample(
    project_id: str,
    payload: StyleSampleCreate,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    embedding = await embedding_service.embed(payload.content)
    entry = await StyleSampleRepository(db).create(
        organization_id=tenant.organization_id,
        project_id=project_id,
        label=payload.label,
        content=payload.content,
        embedding=embedding,
        created_by=user.id,
    )
    await db.commit()
    return entry


@router.delete("/{sample_id}", status_code=204)
async def delete_style_sample(
    project_id: str,
    sample_id: str,
    tenant: TenantDep,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "project:update", tenant)
    repo = StyleSampleRepository(db)
    row = await repo.get(sample_id, organization_id=tenant.organization_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("style_sample_not_found", code="style_sample_not_found")
    await repo.delete(sample_id, organization_id=tenant.organization_id)
    await db.commit()
