"""创作方向预览服务。

为用户在生成完整 Story Bible 之前，提供 3 个候选"故事方向"卡片，
让其先确认大方向再投入额度。

设计原则：
- 生产默认走真实模型，用 schema 生成 3 个候选方向。
- Mock 只允许在自动化测试中显式开启，不进入生产链路。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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


_DIRECTION_TEMPLATES: dict[str, list[StoryDirection]] = {
    "悬疑": [
        StoryDirection(
            name="案件驱动 · 强推理",
            summary="围绕一桩主线案件展开，多视角推进调查，每章一个钩子。",
            selling_points=["案件结构紧凑", "悬念密度高", "适合短中篇"],
            risk="如果章节过长，需要在中段补充支线案件维持新鲜感。",
            recommended=True,
        ),
        StoryDirection(
            name="角色驱动 · 心理悬疑",
            summary="主角内心创伤推动剧情，谜团与人物弧光双线并进。",
            selling_points=["人物厚度强", "情感共鸣度高", "适合改编"],
            risk="节奏偏慢，需要细致铺垫，对作者节奏感要求高。",
            recommended=False,
        ),
        StoryDirection(
            name="社会派 · 群像悬疑",
            summary="多线案件折射社会议题，群像视角推进，案件背后是制度问题。",
            selling_points=["立意深度", "可衍生续作", "话题性强"],
            risk="议题过显可能让悬疑性变弱，需要平衡。",
            recommended=False,
        ),
    ],
    "幻想": [
        StoryDirection(
            name="低魔成长 · 古典史诗",
            summary="魔法稀缺、世界规则严密，主角从凡人开始一步步揭开真相。",
            selling_points=["规则感强", "经典套路稳", "适合长篇"],
            risk="前期节奏可能偏慢，需要钩子撑场。",
            recommended=True,
        ),
        StoryDirection(
            name="高魔战斗 · 升级流",
            summary="魔法体系丰富，主角拥有独特天赋，强战斗刻画 + 阶段性 BOSS。",
            selling_points=["爽点密集", "适合连载", "易出衍生作"],
            risk="容易陷入数值堆砌，需要情感线兜底。",
            recommended=False,
        ),
        StoryDirection(
            name="幻想城邦 · 政治权谋",
            summary="魔法与政治交织，多势力博弈，主角在阵营中艰难抉择。",
            selling_points=["世界观厚重", "权谋戏精彩", "受众成熟"],
            risk="信息量大，开篇需要降低读者门槛。",
            recommended=False,
        ),
    ],
    "校园": [
        StoryDirection(
            name="日常治愈 · 群像青春",
            summary="围绕几个核心角色的日常展开，淡淡的成长与遗憾。",
            selling_points=["共鸣度高", "情绪丰沛", "受众广"],
            risk="缺乏强冲突，需要靠生活细节撑长度。",
            recommended=True,
        ),
        StoryDirection(
            name="校园悬疑 · 怪谈追查",
            summary="学校里发生异常事件，主角和伙伴一起追查真相。",
            selling_points=["年轻气盛感", "钩子明显", "节奏快"],
            risk="设定要自洽，避免悬疑解释跑偏。",
            recommended=False,
        ),
        StoryDirection(
            name="校园奇幻 · 系统觉醒",
            summary="主角在校园中觉醒能力，从日常滑入幻想冒险。",
            selling_points=["反差感强", "可拓展性大", "适合改编"],
            risk="奇幻设定与校园日常的平衡是关键。",
            recommended=False,
        ),
    ],
}


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
        settings = get_settings()
        if settings.model_gateway_allow_mock and settings.model_gateway_mode == "mock":
            return self._mock(project, topic, protagonist_archetype, forbidden_themes)
        return await self._real(
            session,
            project=project,
            topic=topic,
            protagonist_archetype=protagonist_archetype,
            reference_works=reference_works,
            forbidden_themes=forbidden_themes,
            tenant=tenant,
        )

    def _mock(
        self,
        project: Project,
        topic: str,
        protagonist_archetype: str,
        forbidden_themes: list[str],
    ) -> list[StoryDirection]:
        """按 genre 关键词匹配模板，叠加 topic / 主角原型做最小定制。"""
        templates = self._templates_for_genre(project.genre)
        topic_label = topic.strip() or project.title or "新故事"
        out: list[StoryDirection] = []
        for t in templates:
            summary = t.summary
            if topic.strip():
                summary = f"以「{topic_label}」为题材：{summary}"
            if protagonist_archetype.strip():
                summary += f" 主角原型：{protagonist_archetype.strip()}。"
            selling_points = list(t.selling_points)
            risk = t.risk
            if forbidden_themes:
                risk += f" 已自动规避禁忌：{'、'.join(forbidden_themes)}。"
            out.append(
                StoryDirection(
                    name=t.name,
                    summary=summary,
                    selling_points=selling_points,
                    risk=risk,
                    recommended=t.recommended,
                )
            )
        return out

    @staticmethod
    def _templates_for_genre(genre: str) -> list[StoryDirection]:
        if not genre:
            return _DIRECTION_TEMPLATES["幻想"]
        for keyword, templates in _DIRECTION_TEMPLATES.items():
            if keyword in genre:
                return templates
        # 无匹配关键字时给一个通用方向集（直接借幻想模板，名字会带 topic 定制）
        return _DIRECTION_TEMPLATES["幻想"]

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
