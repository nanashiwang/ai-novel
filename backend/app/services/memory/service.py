from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.character import Character
from app.models.draft_version import DraftVersion
from app.models.memory import MemoryEntry
from app.models.scene import Scene
from app.repositories import CharacterRepository, MemoryRepository
from app.schemas.story_generation import (
    CharacterStateUpdateContract,
    CharacterStateUpdateItem,
)
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager

_PROMPT_UPDATE_CHARACTER_STATES = "memory/update_character_states"
_PROMPT_VERSION = "v1"
_logger = logging.getLogger(__name__)


class MemoryService:
    async def update_character_states_from_scene(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        chapter: Chapter,
        scene: Scene,
        draft: DraftVersion,
    ) -> dict[str, Any]:
        """Extract dynamic character memory from a drafted scene and persist it.

        Static character traits stay unchanged. Only relationships/current_state and
        character_state memory entries are updated.
        """
        characters = list(
            await CharacterRepository(session).list(
                organization_id=organization_id,
                project_id=project_id,
                limit=80,
                order_by=Character.created_at.asc(),
            )
        )
        if not characters:
            return {"updated_character_count": 0, "memory_count": 0, "skipped": True}

        try:
            contract = await self._extract_character_state_updates(
                session,
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                chapter=chapter,
                scene=scene,
                draft=draft,
                characters=characters,
            )
        except Exception:  # pragma: no cover - defensive fallback
            _logger.warning("character_state_extraction_failed", exc_info=True)
            contract = self._fallback_character_state_updates(chapter, scene)

        updated, memory_count = await self._apply_character_state_updates(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            updates=contract.updates,
            characters=characters,
        )
        return {
            "updated_character_count": updated,
            "memory_count": memory_count,
            "skipped": False,
        }

    async def _extract_character_state_updates(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        chapter: Chapter,
        scene: Scene,
        draft: DraftVersion,
        characters: list[Character],
    ) -> CharacterStateUpdateContract:
        prompt = prompt_manager.load(_PROMPT_UPDATE_CHARACTER_STATES, version=_PROMPT_VERSION)
        roster = [
            {
                "name": character.name,
                "role": character.role,
                "description": character.description,
                "personality": character.personality,
                "motivation": character.motivation,
                "secret": character.secret,
                "arc": character.arc,
                "relationships": character.relationships or {},
                "current_state": character.current_state or {},
            }
            for character in characters
        ]
        scene_payload = {
            "chapter_index": chapter.chapter_index,
            "chapter_title": chapter.title,
            "scene_index": scene.scene_index,
            "scene_title": scene.title,
            "location": scene.location,
            "characters": scene.characters or [],
            "goal": scene.goal,
            "conflict": scene.conflict,
            "emotion_start": scene.emotion_start,
            "emotion_end": scene.emotion_end,
            "reveal": scene.reveal,
            "hook": scene.hook,
            "draft_excerpt": draft.content[:6000],
        }
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="update_character_states",
            system_prompt=prompt,
            user_prompt=(
                "已有人物名册：\n"
                + json.dumps(roster, ensure_ascii=False)
                + "\n\n当前 scene：\n"
                + json.dumps(scene_payload, ensure_ascii=False)
            ),
            schema=CharacterStateUpdateContract.model_json_schema(),
            prompt_key=_PROMPT_UPDATE_CHARACTER_STATES,
            prompt_version=_PROMPT_VERSION,
            temperature=0.2,
            metadata={"scene_id": scene.id, "chapter_id": chapter.id},
        )
        contract = CharacterStateUpdateContract.model_validate(raw)
        if not contract.updates:
            return self._fallback_character_state_updates(chapter, scene)
        return contract

    def _fallback_character_state_updates(
        self,
        chapter: Chapter,
        scene: Scene,
    ) -> CharacterStateUpdateContract:
        updates: list[CharacterStateUpdateItem] = []
        for name in scene.characters or []:
            clean_name = str(name).strip()
            if not clean_name:
                continue
            state = {
                "last_chapter_index": chapter.chapter_index,
                "last_chapter_title": chapter.title,
                "last_scene_index": scene.scene_index,
                "last_scene_title": scene.title,
                "location": scene.location,
                "recent_goal": scene.goal,
                "recent_conflict": scene.conflict,
                "emotional_state": self._join_transition(
                    scene.emotion_start,
                    scene.emotion_end,
                ),
                "knowledge_state": scene.reveal,
                "last_hook": scene.hook,
            }
            updates.append(
                CharacterStateUpdateItem(
                    name=clean_name,
                    current_state={key: value for key, value in state.items() if value},
                    relationships={},
                    summary=(
                        f"{clean_name}在《{chapter.title}》的“{scene.title}”中经历："
                        f"{scene.conflict or scene.goal or '剧情推进'}。"
                    ),
                )
            )
        return CharacterStateUpdateContract(updates=updates)

    async def _apply_character_state_updates(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        chapter: Chapter,
        scene: Scene,
        updates: list[CharacterStateUpdateItem],
        characters: list[Character],
    ) -> tuple[int, int]:
        by_name = {character.name: character for character in characters}
        memory_repo = MemoryRepository(session)
        await self._delete_scene_character_state_memories(
            session,
            organization_id=organization_id,
            project_id=project_id,
            scene_id=scene.id,
        )

        updated = 0
        memory_count = 0
        seen_names: set[str] = set()
        for item in updates:
            name = item.name.strip()
            if not name or name in seen_names:
                continue
            character = by_name.get(name)
            if not character:
                continue
            seen_names.add(name)

            merged_state = dict(character.current_state or {})
            merged_state.update(item.current_state or {})
            merged_state.setdefault("last_chapter_index", chapter.chapter_index)
            merged_state.setdefault("last_chapter_title", chapter.title)
            merged_state.setdefault("last_scene_index", scene.scene_index)
            merged_state.setdefault("last_scene_title", scene.title)
            merged_state.setdefault("last_scene_id", scene.id)
            character.current_state = merged_state

            merged_relationships = dict(character.relationships or {})
            merged_relationships.update(item.relationships or {})
            character.relationships = merged_relationships
            updated += 1

            content = item.summary or json.dumps(
                {
                    "current_state": merged_state,
                    "relationships": item.relationships,
                },
                ensure_ascii=False,
            )
            await memory_repo.create(
                organization_id=organization_id,
                project_id=project_id,
                source_type="scene",
                source_id=scene.id,
                memory_type="character_state",
                title=f"{name} 状态更新",
                content=content,
                importance=4,
            )
            memory_count += 1

        return updated, memory_count

    async def _delete_scene_character_state_memories(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        scene_id: str,
    ) -> None:
        stmt = select(MemoryEntry).where(
            MemoryEntry.organization_id == organization_id,
            MemoryEntry.project_id == project_id,
            MemoryEntry.source_type == "scene",
            MemoryEntry.source_id == scene_id,
            MemoryEntry.memory_type == "character_state",
        )
        rows = list((await session.execute(stmt)).scalars().all())
        for row in rows:
            await session.delete(row)
        if rows:
            await session.flush()

    @staticmethod
    def _join_transition(start: str, end: str) -> str:
        if start and end:
            return f"{start} → {end}"
        return start or end or ""


memory_service = MemoryService()
