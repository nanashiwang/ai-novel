from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.project import NovelSpec, Project
from app.schemas.story_generation import (
    ChapterPlanContract,
    ChapterPlanItem,
    ScenePlanContract,
    ScenePlanItem,
    StoryBibleContract,
)
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager


class NovelPlannerService:
    async def generate_story_bible(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        project: Project,
        topic: str = "",
    ) -> StoryBibleContract:
        prompt = prompt_manager.load("bible/generate_story_bible")
        user_prompt = (
            "请从上到下生成小说故事圣经。\n"
            f"初始题材/topic：{topic or project.title}\n"
            f"项目标题：{project.title}\n"
            f"类型：{project.genre}\n"
            f"目标读者：{project.target_reader}\n"
            f"目标字数：{project.target_word_count}\n"
            f"目标章节数：{project.target_chapter_count}\n"
            f"文风：{project.style}\n"
            "要求：只返回 JSON，字段必须可直接落库。"
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="generate_story_bible",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema=StoryBibleContract.model_json_schema(),
            metadata={"module": "novel_planner"},
        )
        return self._normalize_story_bible(StoryBibleContract.model_validate(raw), project, topic)

    async def plan_chapters(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        project: Project,
        bible: StoryBibleContract | NovelSpec,
        target_chapters: int,
    ) -> ChapterPlanContract:
        prompt = prompt_manager.load("outline/plan_chapters")
        target_chapters = max(1, target_chapters)
        user_prompt = (
            "请把故事圣经拆成章节大纲，采用三幕式推进，但不要输出幕名层级。\n"
            f"目标章节数：{target_chapters}\n"
            f"项目：{project.title}\n"
            f"故事圣经：\n{self._dump_contract(bible)}\n"
            "要求：每章必须有明确目标、冲突、结尾钩子；只返回 JSON。"
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="plan_chapters",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema=ChapterPlanContract.model_json_schema(),
            metadata={"module": "novel_planner", "target_chapters": target_chapters},
        )
        contract = ChapterPlanContract.model_validate(raw)
        if not contract.chapters:
            return self._fallback_chapters(project, bible, target_chapters)
        return self._normalize_chapters(contract)

    async def plan_scenes(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        project: Project,
        bible: StoryBibleContract | NovelSpec,
        chapter: Chapter,
        scenes_per_chapter: int,
        expected_words: int,
    ) -> ScenePlanContract:
        prompt = prompt_manager.load("outline/plan_scenes")
        scenes_per_chapter = max(1, scenes_per_chapter)
        user_prompt = (
            "请把指定章节拆成 scene cards。\n"
            f"项目：{project.title}\n"
            f"故事圣经：\n{self._dump_contract(bible)}\n"
            f"章节：第 {chapter.chapter_index} 章《{chapter.title}》\n"
            f"章节摘要：{chapter.summary}\n"
            f"章节目标：{chapter.goal}\n"
            f"章节冲突：{chapter.conflict}\n"
            f"结尾钩子：{chapter.ending_hook}\n"
            f"建议场景数：{scenes_per_chapter}\n"
            f"单场景目标字数：{expected_words}\n"
            "要求：每个 scene 必须有微冲突、情绪变化、揭示与钩子；只返回 JSON。"
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="plan_scenes",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema=ScenePlanContract.model_json_schema(),
            metadata={
                "module": "novel_planner",
                "chapter_id": chapter.id,
                "scenes_per_chapter": scenes_per_chapter,
            },
        )
        contract = ScenePlanContract.model_validate(raw)
        if not contract.scenes:
            return self._fallback_scenes(chapter, scenes_per_chapter, expected_words)
        return self._normalize_scenes(contract, chapter, expected_words)

    def _normalize_story_bible(
        self,
        bible: StoryBibleContract,
        project: Project,
        topic: str,
    ) -> StoryBibleContract:
        data = bible.model_dump()
        data["premise"] = data["premise"] or topic or project.title
        data["genre"] = data["genre"] or project.genre or "类型小说"
        data["target_reader"] = data["target_reader"] or project.target_reader or "中文小说读者"
        data["tone"] = data["tone"] or project.style or "节奏明确，情绪递进"
        data["theme"] = data["theme"] or "人物在关键选择中完成转变"
        data["narrative_pov"] = data["narrative_pov"] or "第三人称有限视角"
        data["style_guide"] = (
            data["style_guide"] or project.style or "中文叙事，重视画面、冲突和章节钩子"
        )
        constraints = list(data.get("constraints") or [])
        if project.target_word_count:
            constraints.append(f"目标总字数约 {project.target_word_count} 字")
        if project.target_chapter_count:
            constraints.append(f"目标章节数约 {project.target_chapter_count} 章")
        data["constraints"] = constraints
        return StoryBibleContract(**data)

    def _fallback_chapters(
        self,
        project: Project,
        bible: StoryBibleContract | NovelSpec,
        target_chapters: int,
    ) -> ChapterPlanContract:
        premise = getattr(bible, "premise", "") or project.title
        chapters: list[ChapterPlanItem] = []
        for index in range(1, target_chapters + 1):
            if index <= max(1, target_chapters // 3):
                phase = "开局"
            elif index <= max(2, target_chapters * 2 // 3):
                phase = "对抗"
            else:
                phase = "收束"
            chapters.append(
                ChapterPlanItem(
                    chapter_index=index,
                    title=f"第{index}章 {phase}转折",
                    summary=f"围绕“{premise}”推进第 {index} 个关键事件。",
                    goal="推进主线并制造新的选择压力。",
                    conflict="主角目标与外部阻力正面碰撞。",
                    ending_hook="新的线索或危机在章末出现。",
                )
            )
        return ChapterPlanContract(chapters=chapters)

    def _fallback_scenes(
        self,
        chapter: Chapter,
        scenes_per_chapter: int,
        expected_words: int,
    ) -> ScenePlanContract:
        scenes: list[ScenePlanItem] = []
        for index in range(1, scenes_per_chapter + 1):
            scenes.append(
                ScenePlanItem(
                    scene_index=index,
                    title=f"{chapter.title}·场景{index}",
                    time_marker="承接上一场",
                    location="核心事件地点",
                    characters=[],
                    goal=f"完成第 {index} 个场景推进点。",
                    conflict="信息差、时间压力或人物立场冲突升级。",
                    emotion_start="紧张",
                    emotion_end="更强的不确定感",
                    reveal="暴露一个新的事实或人物态度。",
                    hook="留下下一场必须回应的问题。",
                    expected_words=expected_words,
                )
            )
        return ScenePlanContract(
            chapter_index=chapter.chapter_index,
            chapter_title=chapter.title,
            scenes=scenes,
        )

    def _normalize_chapters(self, contract: ChapterPlanContract) -> ChapterPlanContract:
        chapters = []
        for index, item in enumerate(contract.chapters, start=1):
            data = item.model_dump()
            data["chapter_index"] = data.get("chapter_index") or index
            data["title"] = data.get("title") or f"第{index}章"
            chapters.append(ChapterPlanItem(**data))
        return ChapterPlanContract(chapters=chapters)

    def _normalize_scenes(
        self,
        contract: ScenePlanContract,
        chapter: Chapter,
        expected_words: int,
    ) -> ScenePlanContract:
        scenes = []
        for index, item in enumerate(contract.scenes, start=1):
            data = item.model_dump()
            data["scene_index"] = data.get("scene_index") or index
            data["title"] = data.get("title") or f"{chapter.title}·场景{index}"
            data["expected_words"] = data.get("expected_words") or expected_words
            scenes.append(ScenePlanItem(**data))
        return ScenePlanContract(
            chapter_index=contract.chapter_index or chapter.chapter_index,
            chapter_title=contract.chapter_title or chapter.title,
            scenes=scenes,
        )

    def _dump_contract(self, value: StoryBibleContract | NovelSpec) -> str:
        if hasattr(value, "model_dump"):
            return json.dumps(value.model_dump(), ensure_ascii=False, indent=2)
        payload = {
            "premise": value.premise,
            "theme": value.theme,
            "genre": value.genre,
            "tone": value.tone,
            "target_reader": value.target_reader,
            "narrative_pov": value.narrative_pov,
            "style_guide": value.style_guide,
            "constraints": value.constraints,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


novel_planner_service = NovelPlannerService()
