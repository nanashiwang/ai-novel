"""Backfill story_state_items from existing latest scene drafts.

Usage inside the backend container:

    python -m app.scripts.backfill_story_states --project-id project_xxx
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.chapter import Chapter
from app.models.draft_version import DraftVersion
from app.models.project import Project
from app.models.scene import Scene
from app.repositories import ProjectRepository
from app.services.story_state.extract import extract_story_state_from_scene


async def _latest_draft(session, *, organization_id: str, scene_id: str) -> DraftVersion | None:
    result = await session.execute(
        select(DraftVersion)
        .where(
            DraftVersion.organization_id == organization_id,
            DraftVersion.scene_id == scene_id,
        )
        .order_by(DraftVersion.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _project_ids(session, organization_id: str | None, project_id: str | None) -> list[str]:
    if project_id:
        return [project_id]
    stmt = select(Project.id)
    if organization_id:
        stmt = stmt.where(Project.organization_id == organization_id)
    rows = (await session.execute(stmt.order_by(Project.updated_at.desc()))).all()
    return [row[0] for row in rows]


async def _ordered_scenes(
    session,
    *,
    organization_id: str,
    project_id: str,
    limit: int | None,
    chapter_from: int | None,
    chapter_to: int | None,
) -> list[tuple[Scene, Chapter]]:
    stmt = (
        select(Scene, Chapter)
        .join(Chapter, Chapter.id == Scene.chapter_id)
        .where(
            Scene.organization_id == organization_id,
            Scene.project_id == project_id,
        )
    )
    if chapter_from is not None:
        stmt = stmt.where(Chapter.chapter_index >= chapter_from)
    if chapter_to is not None:
        stmt = stmt.where(Chapter.chapter_index <= chapter_to)
    stmt = stmt.order_by(Chapter.chapter_index.asc(), Scene.scene_index.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


def _scene_ref(chapter: Chapter, scene: Scene) -> dict[str, Any]:
    return {
        "chapter_id": chapter.id,
        "chapter_index": chapter.chapter_index,
        "chapter_title": chapter.title,
        "scene_id": scene.id,
        "scene_index": scene.scene_index,
        "scene_title": scene.title,
    }


async def _scene_has_state_items(
    session,
    *,
    organization_id: str,
    project_id: str,
    scene_id: str,
) -> bool:
    from app.models.story_state_item import StoryStateItem  # noqa: PLC0415

    result = await session.execute(
        select(StoryStateItem.id)
        .where(
            StoryStateItem.organization_id == organization_id,
            StoryStateItem.project_id == project_id,
            StoryStateItem.source_scene_id == scene_id,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def backfill_story_states(
    *,
    organization_id: str | None,
    project_id: str | None,
    limit: int | None,
    chapter_from: int | None,
    chapter_to: int | None,
    skip_existing: bool,
    dry_run: bool,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "projects": 0,
        "scenes_seen": 0,
        "scenes_with_draft": 0,
        "scenes_skipped_existing": 0,
        "scenes_processed": 0,
        "upserted_count": 0,
        "changed_count": 0,
        "requirement_count": 0,
        "chapter_from": chapter_from,
        "chapter_to": chapter_to,
        "skip_existing": skip_existing,
        "errors": [],
        "dry_run": dry_run,
    }
    async with AsyncSessionLocal() as session:
        project_ids = await _project_ids(session, organization_id, project_id)
        for pid in project_ids:
            project = await ProjectRepository(session).get(pid, organization_id=organization_id)
            if not project:
                summary["errors"].append({"project_id": pid, "error": "project_not_found"})
                continue
            summary["projects"] += 1
            scenes = await _ordered_scenes(
                session,
                organization_id=project.organization_id,
                project_id=project.id,
                limit=limit,
                chapter_from=chapter_from,
                chapter_to=chapter_to,
            )
            for scene, chapter in scenes:
                summary["scenes_seen"] += 1
                draft = await _latest_draft(
                    session,
                    organization_id=project.organization_id,
                    scene_id=scene.id,
                )
                if not draft:
                    continue
                summary["scenes_with_draft"] += 1
                if skip_existing and await _scene_has_state_items(
                    session,
                    organization_id=project.organization_id,
                    project_id=project.id,
                    scene_id=scene.id,
                ):
                    summary["scenes_skipped_existing"] += 1
                    continue
                if dry_run:
                    continue
                try:
                    result = await extract_story_state_from_scene(
                        session,
                        organization_id=project.organization_id,
                        project_id=project.id,
                        job_id=f"story_state_backfill_{scene.id}",
                        chapter=chapter,
                        scene=scene,
                        draft=draft,
                        created_by="story_state_backfill",
                    )
                    await session.commit()
                    summary["scenes_processed"] += 1
                    summary["upserted_count"] += int(result.get("upserted_count") or 0)
                    summary["changed_count"] += int(result.get("changed_count") or 0)
                    summary["requirement_count"] += int(
                        result.get("requirement_count") or 0
                    )
                    if result.get("error"):
                        summary["errors"].append(_scene_ref(chapter, scene) | {
                            "error": result.get("error")
                        })
                except Exception as exc:  # noqa: BLE001 - backfill should continue
                    await session.rollback()
                    summary["errors"].append(_scene_ref(chapter, scene) | {
                        "error": str(exc) or exc.__class__.__name__,
                    })
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--chapter-from", type=int, default=None)
    parser.add_argument("--chapter-to", type=int, default=None)
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip scenes that already produced at least one story_state_item.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    summary = await backfill_story_states(
        organization_id=args.organization_id,
        project_id=args.project_id,
        limit=args.limit,
        chapter_from=args.chapter_from,
        chapter_to=args.chapter_to,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
