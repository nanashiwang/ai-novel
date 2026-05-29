from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_platform_admin
from app.repositories import ContinuityIssueRepository

router = APIRouter(prefix="/admin/content-reviews", tags=["admin-content-reviews"])


@router.get("")
async def content_reviews(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    rows = await ContinuityIssueRepository(db).list(limit=200)
    return [
        {
            "id": r.id,
            "organization_id": r.organization_id,
            "project_id": r.project_id,
            "story_state_item_id": r.story_state_item_id,
            "issue_type": r.issue_type,
            "severity": r.severity,
            "description": r.description,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in rows
    ]
