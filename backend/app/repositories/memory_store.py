from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.models.common import new_id

NOW = datetime.now(timezone.utc).isoformat()

DB: dict[str, list[dict[str, Any]]] = {
    "projects": [
        {
            "id": "demo-project",
            "organization_id": "org_personal",
            "created_by": "user_writer",
            "title": "雾都归档人",
            "genre": "悬疑 · 都市",
            "target_word_count": 300000,
            "target_chapter_count": 48,
            "language": "zh-CN",
            "style": "冷峻克制，细节密集",
            "status": "drafting",
        }
    ],
    "plans": [
        {
            "code": "Free",
            "name": "Free",
            "description": "免费体验",
            "price_monthly": 0,
            "status": "active",
        },
        {
            "code": "Pro",
            "name": "Pro",
            "description": "长篇小说自动生产",
            "price_monthly": 129,
            "status": "active",
        },
        {
            "code": "Team",
            "name": "Team",
            "description": "团队协作与 API",
            "price_monthly": 399,
            "status": "active",
        },
    ],
    "quota_balances": [
        {
            "id": "quota_words",
            "organization_id": "org_personal",
            "quota_key": "monthly_generated_words",
            "limit_value": 1000000,
            "used_value": 682450,
            "reserved_value": 42000,
            "reset_at": "2026-06-01",
        },
        {
            "id": "quota_review",
            "organization_id": "org_personal",
            "quota_key": "monthly_review_count",
            "limit_value": 300,
            "used_value": 183,
            "reserved_value": 6,
            "reset_at": "2026-06-01",
        },
    ],
    "generation_jobs": [],
    "quota_reservations": [],
    "model_calls": [],
    "usage_events": [],
    "admin_audit_logs": [],
}


def list_rows(table: str, organization_id: str | None = None) -> list[dict[str, Any]]:
    rows = deepcopy(DB.get(table, []))
    if organization_id:
        rows = [row for row in rows if row.get("organization_id") == organization_id]
    return rows


def get_row(table: str, row_id: str, organization_id: str | None = None) -> dict[str, Any] | None:
    for row in DB.get(table, []):
        if row.get("id") == row_id and (
            organization_id is None or row.get("organization_id") == organization_id
        ):
            return deepcopy(row)
    return None


def insert_row(table: str, row: dict[str, Any], prefix: str) -> dict[str, Any]:
    item = deepcopy(row)
    item.setdefault("id", new_id(prefix))
    item.setdefault("created_at", NOW)
    item.setdefault("updated_at", NOW)
    DB.setdefault(table, []).append(item)
    return deepcopy(item)


def update_row(
    table: str,
    row_id: str,
    values: dict[str, Any],
    organization_id: str | None = None,
) -> dict[str, Any] | None:
    for row in DB.get(table, []):
        if row.get("id") == row_id and (
            organization_id is None or row.get("organization_id") == organization_id
        ):
            row.update(values)
            row["updated_at"] = datetime.now(timezone.utc).isoformat()
            return deepcopy(row)
    return None
