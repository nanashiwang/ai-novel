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

# Prompt 标识与版本：作为常量集中，便于版本号升级与 model_calls 表追溯。
# 修改这里的版本号 → prompt 文件命名 → model_calls.prompt_version 同步生效。
_PROMPT_STORY_BIBLE = "bible/generate_story_bible"
_PROMPT_PLAN_CHAPTERS = "outline/plan_chapters"
_PROMPT_PLAN_SCENES = "outline/plan_scenes"
_PROMPT_VERSION = "v1"


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
        creative_prefs: dict | None = None,
    ) -> StoryBibleContract:
        prompt = prompt_manager.load(_PROMPT_STORY_BIBLE, version=_PROMPT_VERSION)
        prefs = creative_prefs or {}
        protagonist = (prefs.get("protagonist_archetype") or "").strip()
        references = [s for s in (prefs.get("reference_works") or []) if s.strip()]
        forbidden = [s for s in (prefs.get("forbidden_themes") or []) if s.strip()]
        temperature = prefs.get("temperature")
        # 默认 0.7：足够发挥但不会偏离 schema；用户可在 0~1.5 内自调
        if temperature is None:
            temperature = 0.7

        # 拼装 user_prompt：项目字段一定加，创作偏好按存在与否选择性加
        lines: list[str] = [
            "请从上到下生成小说故事圣经。",
            f"初始题材/topic：{topic or project.title}",
            f"项目标题：{project.title}",
            f"类型：{project.genre}",
            f"目标读者：{project.target_reader}",
            f"目标字数：{project.target_word_count}",
            f"目标章节数：{project.target_chapter_count}",
            f"文风：{project.style}",
        ]
        if protagonist:
            lines.append(f"主角原型/期望：{protagonist}")
        if references:
            lines.append(f"参考作品（仅做风格参考，不要照搬人物/情节）：{', '.join(references)}")
        if forbidden:
            lines.append(f"禁忌主题（绝对不要出现）：{', '.join(forbidden)}")
        lines.append("要求：只返回 JSON，字段必须可直接落库。")
        user_prompt = "\n".join(lines)

        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="generate_story_bible",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema=StoryBibleContract.model_json_schema(),
            prompt_key=_PROMPT_STORY_BIBLE,
            prompt_version=_PROMPT_VERSION,
            temperature=float(temperature),
            metadata={"module": "novel_planner", "has_prefs": bool(prefs)},
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
        start_chapter_index: int = 1,
        end_chapter_index: int | None = None,
        character_roster: str = "",
    ) -> ChapterPlanContract:
        prompt = prompt_manager.load(_PROMPT_PLAN_CHAPTERS, version=_PROMPT_VERSION)
        target_total_chapters = max(1, target_chapters)
        start_chapter_index = max(1, start_chapter_index)
        end_chapter_index = max(
            start_chapter_index,
            int(end_chapter_index or target_total_chapters),
        )
        batch_count = end_chapter_index - start_chapter_index + 1
        roster_block = (
            f"\n\n已登记人物名册（章节主线人物、同桌/师生等关系必须与这里一致；"
            f"不要凭空替换主线角色姓名）：\n{character_roster}"
            if character_roster
            else ""
        )
        user_prompt = (
            "请把故事圣经拆成章节大纲，采用三幕式推进，但不要输出幕名层级。\n"
            f"全书目标章节数：{target_total_chapters}\n"
            f"本次只生成第 {start_chapter_index} 章到第 {end_chapter_index} 章，"
            f"共 {batch_count} 章；不要输出其他章节。\n"
            f"项目：{project.title}\n"
            f"故事圣经：\n{self._dump_contract(bible)}\n"
            f"{roster_block}\n"
            "要求：chapter_index 必须使用实际章节序号；每章必须有明确目标、冲突、"
            "结尾钩子；只返回 JSON。"
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
            prompt_key=_PROMPT_PLAN_CHAPTERS,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "module": "novel_planner",
                "target_chapters": target_total_chapters,
                "start_chapter_index": start_chapter_index,
                "end_chapter_index": end_chapter_index,
            },
        )
        contract = ChapterPlanContract.model_validate(raw)
        if not contract.chapters:
            return self._fallback_chapters(
                project,
                bible,
                start_chapter_index=start_chapter_index,
                target_chapters=end_chapter_index,
            )
        return self._normalize_chapters(contract, start_chapter_index=start_chapter_index)

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
        scenes_per_chapter: int | None,
        expected_words: int,
        character_roster: str = "",
    ) -> ScenePlanContract:
        prompt = prompt_manager.load(_PROMPT_PLAN_SCENES, version=_PROMPT_VERSION)
        scenes_per_chapter = (
            max(1, min(scenes_per_chapter, 8)) if scenes_per_chapter is not None else None
        )
        scene_count_instruction = (
            f"建议场景数：{scenes_per_chapter}\n"
            if scenes_per_chapter is not None
            else "场景数：请根据本章复杂度自行判断，范围 1-8 个；过渡章少，高潮/群像章多。\n"
        )
        roster_block = (
            f"\n已登记人物名册（scene 出场人物必须优先从这里选择，不要凭空替换主线角色姓名）：\n"
            f"{character_roster}\n"
            if character_roster
            else ""
        )
        user_prompt = (
            "请把指定章节拆成 scene cards。\n"
            f"项目：{project.title}\n"
            f"故事圣经：\n{self._dump_contract(bible)}\n"
            f"{roster_block}"
            f"章节：第 {chapter.chapter_index} 章《{chapter.title}》\n"
            f"章节摘要：{chapter.summary}\n"
            f"章节目标：{chapter.goal}\n"
            f"章节冲突：{chapter.conflict}\n"
            f"结尾钩子：{chapter.ending_hook}\n"
            f"{scene_count_instruction}"
            f"单场景目标字数：{expected_words}\n"
            "要求：每个 scene 必须有 scene_purpose、entry_state、exit_state、"
            "must_include、must_avoid、微冲突、情绪变化、揭示与钩子；"
            "相邻场景必须顺序承接，避免重复上一场已完成的信息；只返回 JSON。"
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
            prompt_key=_PROMPT_PLAN_SCENES,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "module": "novel_planner",
                "chapter_id": chapter.id,
                "scenes_per_chapter": scenes_per_chapter,
                "scene_count_mode": "manual" if scenes_per_chapter is not None else "auto",
            },
        )
        contract = ScenePlanContract.model_validate(raw)
        if not contract.scenes:
            return self._fallback_scenes(
                chapter,
                scenes_per_chapter or self._infer_scene_count(chapter),
                expected_words,
            )
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
        characters: list[dict] = []
        for index, character in enumerate(data.get("main_characters") or [], start=1):
            item = dict(character)
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            role = str(
                item.get("role") or ("protagonist" if index == 1 else "supporting")
            ).strip()
            item["name"] = name
            item["role"] = role
            item["description"] = str(item.get("description") or f"{name}是推动主线的关键人物。")
            item["personality"] = str(
                item.get("personality") or "在压力下会暴露真实立场与弱点。"
            )
            item["motivation"] = str(
                item.get("motivation") or f"围绕“{data['premise']}”追求自己的目标。"
            )
            item["secret"] = str(
                item.get("secret") or f"{name}隐藏着会影响主线走向的关键信息。"
            )
            item["arc"] = str(item.get("arc") or "在关键选择中完成关系与立场转变。")
            if not isinstance(item.get("relationships"), dict):
                item["relationships"] = {}
            if not isinstance(item.get("current_state"), dict) or not item.get("current_state"):
                item["current_state"] = {
                    "status": "故事开局",
                    "knowledge_state": "尚未掌握核心真相",
                }
            characters.append(item)
        if not characters:
            characters = [
                {
                    "name": "主角",
                    "role": "protagonist",
                    "description": "承担主线行动与情绪变化的核心人物。",
                    "personality": "外表克制，遇到关键选择会主动冒险。",
                    "motivation": f"揭开“{data['premise']}”背后的真相。",
                    "secret": "曾经与核心事件有未公开的联系。",
                    "arc": "从被动卷入到主动承担代价。",
                    "relationships": {},
                    "current_state": {
                        "status": "故事开局",
                        "knowledge_state": "尚未掌握核心真相",
                    },
                },
                {
                    "name": "对立者",
                    "role": "antagonist",
                    "description": "制造主线阻力并代表另一套价值秩序。",
                    "personality": "冷静、强势，擅长利用规则压迫他人。",
                    "motivation": "维护自己认定的秩序与利益。",
                    "secret": "掌握主角尚不知道的旧事真相。",
                    "arc": "从秩序维护者滑向更极端的控制者。",
                    "relationships": {},
                    "current_state": {
                        "status": "暗中布局",
                        "knowledge_state": "掌握部分核心真相",
                    },
                },
            ]
        data["main_characters"] = characters
        if not data.get("locations"):
            data["locations"] = [
                {
                    "name": "核心事件地点",
                    "description": f"承载『{project.title}』主线冲突与关键转折的主要舞台。",
                    "importance": "high",
                }
            ]
        if not data.get("factions"):
            data["factions"] = [
                {
                    "name": "核心对立势力",
                    "description": "推动主线压力、制造阻碍并承载世界秩序的一方势力。",
                    "importance": "high",
                }
            ]
        return StoryBibleContract(**data)

    def _fallback_chapters(
        self,
        project: Project,
        bible: StoryBibleContract | NovelSpec,
        target_chapters: int,
        start_chapter_index: int = 1,
    ) -> ChapterPlanContract:
        premise = getattr(bible, "premise", "") or project.title
        chapters: list[ChapterPlanItem] = []
        for index in range(start_chapter_index, target_chapters + 1):
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
            previous = f"承接场景 {index - 1} 的新信息与情绪压力" if index > 1 else "承接上一章结尾钩子"
            exit_state = (
                f"第 {index} 个推进点完成，但留下新的行动压力"
                if index < scenes_per_chapter
                else "本章目标阶段性完成，并抛出下一章钩子"
            )
            scenes.append(
                ScenePlanItem(
                    scene_index=index,
                    title=f"{chapter.title}·场景{index}",
                    time_marker="承接上一场",
                    location="核心事件地点",
                    characters=[],
                    scene_purpose=f"完成本章第 {index} 个必要推进点。",
                    entry_state=previous,
                    exit_state=exit_state,
                    goal=f"完成第 {index} 个场景推进点。",
                    conflict="信息差、时间压力或人物立场冲突升级。",
                    must_include=["承接上一场结果", "推进本章目标"],
                    must_avoid=["重复解释已解决的信息", "突然改变人物动机"],
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

    def _infer_scene_count(self, chapter: Chapter) -> int:
        text = " ".join(
            [
                chapter.summary or "",
                chapter.goal or "",
                chapter.conflict or "",
                chapter.ending_hook or "",
            ]
        )
        score = 3
        dense_markers = [
            "反转",
            "高潮",
            "决战",
            "群像",
            "多线",
            "潜入",
            "追逐",
            "审判",
            "大战",
        ]
        quiet_markers = ["过渡", "日常", "铺垫", "整理", "休整"]
        if any(marker in text for marker in dense_markers):
            score += 2
        if any(marker in text for marker in quiet_markers):
            score -= 1
        if len(text) > 240:
            score += 1
        return max(1, min(score, 8))

    def _normalize_chapters(
        self,
        contract: ChapterPlanContract,
        *,
        start_chapter_index: int = 1,
    ) -> ChapterPlanContract:
        chapters = []
        for index, item in enumerate(contract.chapters, start=start_chapter_index):
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
            data["scene_purpose"] = data.get("scene_purpose") or data.get("goal") or "推进本章目标"
            data["entry_state"] = data.get("entry_state") or (
                "承接上一场结果" if index > 1 else "承接上一章钩子"
            )
            data["exit_state"] = data.get("exit_state") or data.get("hook") or "留下下一步压力"
            data["must_include"] = data.get("must_include") or ["推进本章目标"]
            data["must_avoid"] = data.get("must_avoid") or ["重复上一场已完成的信息"]
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
