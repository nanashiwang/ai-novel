"""创作方向预览服务。

为用户在生成完整 Story Bible 之前，提供 3 个候选"故事方向"卡片，
让其先确认大方向再投入额度。

设计原则：
- 始终走真实模型，用 schema 生成 3 个候选方向。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.models.project import Project
from app.services.model_gateway.service import model_gateway


@dataclass
class StoryDirection:
    name: str
    summary: str
    selling_points: list[str]
    risk: str
    recommended: bool



class StoryDirectionService:
    async def preview(
        self,
        session: AsyncSession,
        *,
        project: Project,
        topic: str,
        protagonist_archetype: str,
        reference_works: list[str],
        forbidden_themes: list[str],
        tenant: TenantContext,
    ) -> list[StoryDirection]:
        return await self._real(
            session,
            project=project,
            topic=topic,
            protagonist_archetype=protagonist_archetype,
            reference_works=reference_works,
            forbidden_themes=forbidden_themes,
            tenant=tenant,
        )

    async def _real(
        self,
        session: AsyncSession,
        **kwargs: Any,
    ) -> list[StoryDirection]:
        project: Project = kwargs["project"]
        topic = str(kwargs.get("topic") or "")
        protagonist_archetype = str(kwargs.get("protagonist_archetype") or "")
        reference_works = list(kwargs.get("reference_works") or [])
        forbidden_themes = list(kwargs.get("forbidden_themes") or [])
        tenant: TenantContext = kwargs["tenant"]

        user_prompt = "\n".join(
            [
                "请为小说生成 3 个可选创作方向。",
                f"项目标题：{project.title}",
                f"类型：{project.genre}",
                f"目标读者：{project.target_reader}",
                f"目标字数：{project.target_word_count}",
                f"目标章节数：{project.target_chapter_count}",
                f"文风：{project.style}",
                f"创作意图/topic：{topic or project.title}",
                f"主角原型/期望：{protagonist_archetype or '未指定'}",
                f"参考作品：{', '.join(reference_works) if reference_works else '未指定'}",
                f"禁忌主题：{', '.join(forbidden_themes) if forbidden_themes else '无'}",
                "要求：只返回 JSON；directions 必须正好 3 个，且至少 1 个 recommended=true。",
            ]
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=tenant.organization_id,
            project_id=project.id,
            job_id=None,
            task_type="preview_story_directions",
            system_prompt=(
                "你是 NovelFlow AI 的故事开发顾问。请给出可直接用于长篇小说立项的"
                "3 个差异化方向，避免空泛营销话术。"
            ),
            user_prompt=user_prompt,
            schema=self._direction_schema(),
            prompt_key="bible/preview_directions",
            prompt_version="v1",
            temperature=0.8,
        )
        directions = self._normalize_real_response(raw)
        if len(directions) != 3:
            raise ValueError("story_direction_response_requires_three_items")
        if not any(item.recommended for item in directions):
            directions[0].recommended = True
        return directions

    @staticmethod
    def _direction_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directions": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "summary": {"type": "string"},
                            "selling_points": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 2,
                                "maxItems": 5,
                            },
                            "risk": {"type": "string"},
                            "recommended": {"type": "boolean"},
                        },
                        "required": [
                            "name",
                            "summary",
                            "selling_points",
                            "risk",
                            "recommended",
                        ],
                    },
                }
            },
            "required": ["directions"],
        }

    @staticmethod
    def _normalize_real_response(raw: dict[str, Any]) -> list[StoryDirection]:
        items = raw.get("directions")
        if not isinstance(items, list):
            return []
        directions: list[StoryDirection] = []
        for item in items[:3]:
            if not isinstance(item, dict):
                continue
            selling_points = item.get("selling_points") or []
            if not isinstance(selling_points, list):
                selling_points = [str(selling_points)]
            directions.append(
                StoryDirection(
                    name=str(item.get("name") or "未命名方向").strip(),
                    summary=str(item.get("summary") or "").strip(),
                    selling_points=[
                        str(point).strip()
                        for point in selling_points
                        if str(point).strip()
                    ],
                    risk=str(item.get("risk") or "").strip(),
                    recommended=bool(item.get("recommended")),
                )
            )
        return directions


story_direction_service = StoryDirectionService()
