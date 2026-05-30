from __future__ import annotations

import json
import re
from typing import Any


class DeterministicModelProvider:
    """测试专用模型替身：稳定返回结构化内容，不参与生产链路。"""

    @staticmethod
    def _parse_prompt_fields(user_prompt: str) -> dict[str, str]:
        patterns = {
            "title": r"项目标题：([^\n]*)",
            "genre": r"类型：([^\n]*)",
            "target_reader": r"目标读者：([^\n]*)",
            "style": r"文风：([^\n]*)",
            "topic": r"(?:初始题材/topic|创作意图/topic)：([^\n]*)",
            "protagonist": r"主角原型/期望：([^\n]*)",
            "references": r"参考作品[^\n]*：([^\n]*)",
            "forbidden": r"禁忌主题[^\n]*：([^\n]*)",
        }
        out: dict[str, str] = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, user_prompt)
            out[key] = match.group(1).strip() if match else ""
        return out

    @staticmethod
    def _seed_int(text: str) -> int:
        seed = 0
        for ch in text:
            seed = (seed * 131 + ord(ch)) & 0xFFFFFFFF
        return seed

    def _story_bible(self, user_prompt: str) -> dict[str, Any]:
        fields = self._parse_prompt_fields(user_prompt)
        title = fields.get("title") or "未命名小说"
        genre = fields.get("genre") or "悬疑幻想"
        style = fields.get("style") or "画面清晰、冲突明确"
        target_reader = fields.get("target_reader") or "中文长篇类型小说读者"
        topic = fields.get("topic") or title
        protagonist = fields.get("protagonist") or ""
        forbidden = fields.get("forbidden") or ""

        seed = self._seed_int(title)
        name_packs = [
            ("林澈", "沈砚"),
            ("江昼", "苏怀玦"),
            ("沈白川", "宋鹤川"),
        ]
        world_packs = [
            [
                "记忆可以被交易，但会留下情绪残影",
                "城市档案馆记录每一次被篡改的过去",
            ],
            [
                "灵能波动会暴露使用者的真实情感",
                "禁区入口每隔七日会随机迁移一次",
            ],
            [
                "契约印记一旦缔结便会侵蚀缔约者的寿命",
                "梦境与现实在月相满圆时会暂时同步",
            ],
        ]
        protagonist_name, antagonist_name = name_packs[seed % len(name_packs)]
        world_rules = world_packs[seed % len(world_packs)]

        constraints = ["保持世界规则前后一致", "避免无铺垫反转"]
        if forbidden:
            constraints.append(f"严禁出现：{forbidden}")

        protagonist_desc = (
            protagonist or f"在『{title}』中追逐真相的核心角色，专长契合本作题材。"
        )
        return {
            "premise": f"围绕『{topic}』展开，{protagonist_name}在{genre}舞台上追查真相。",
            "theme": "选择、代价与自我救赎",
            "genre": genre,
            "tone": "冷峻、克制、逐步升温",
            "target_reader": target_reader,
            "narrative_pov": "第三人称有限视角",
            "style_guide": style,
            "constraints": constraints,
            "locations": [
                {
                    "name": "雾城档案馆",
                    "description": "保存城市记忆交易记录的核心地点，所有被篡改的过去都会留下索引。",
                    "importance": "high",
                },
                {
                    "name": "七日迁移禁区",
                    "description": "入口每隔七日随机迁移，适合承载追逐、潜入和规则验证场景。",
                    "importance": "medium",
                },
            ],
            "factions": [
                {
                    "name": "城市监察会",
                    "description": "维持记忆交易秩序的权力机构，既保护规则也掩盖旧案。",
                    "importance": "high",
                },
                {
                    "name": "灰市掮客联盟",
                    "description": "游走在合法交易边缘的地下势力，掌握大量非法记忆样本。",
                    "importance": "medium",
                },
            ],
            "world_rules": world_rules,
            "main_characters": [
                {
                    "name": protagonist_name,
                    "role": "protagonist",
                    "description": protagonist_desc,
                    "personality": "克制敏锐，习惯独自承担风险。",
                    "motivation": f"揭开『{topic}』背后被掩盖的真相。",
                    "secret": "曾接触过核心记忆样本，却主动隐瞒了这段经历。",
                    "arc": "从被动卷入到主动承担抉择的代价。",
                    "relationships": {
                        antagonist_name: "被对方监视并逐步形成正面对抗"
                    },
                    "current_state": {
                        "status": "追查真相中",
                        "knowledge_state": "只知道案件表层线索",
                    },
                },
                {
                    "name": antagonist_name,
                    "role": "antagonist",
                    "description": f"掌控本作核心冲突源头的对立面，{style}下的反派形象。",
                    "personality": "冷静强势，擅长用秩序包装私心。",
                    "motivation": "用自己的方式维护被打破的旧秩序。",
                    "secret": "知道旧案真正责任人，并一直操纵证据流向。",
                    "arc": "从秩序维护者滑向掌控一切的人。",
                    "relationships": {
                        protagonist_name: "试图阻止对方接近真相"
                    },
                    "current_state": {
                        "status": "暗中布局",
                        "knowledge_state": "掌握核心真相的一部分",
                    },
                },
            ],
            "continuity_rules": [
                f"{protagonist_name}不能直接想起核心真相",
                "关键设定必须付出等价代价",
            ],
            "plot_threads": [
                f"{topic}的真相追查",
                "对立面的隐藏布局",
                "世界规则的边界探索",
            ],
        }

    def _directions(self, user_prompt: str) -> dict[str, Any]:
        fields = self._parse_prompt_fields(user_prompt)
        topic = fields.get("topic") or fields.get("title") or "新故事"
        protagonist = fields.get("protagonist") or "核心主角"
        forbidden = fields.get("forbidden") or ""
        risk_suffix = f" 已规避禁忌：{forbidden}。" if forbidden and forbidden != "无" else ""
        return {
            "directions": [
                {
                    "name": "强情节推进",
                    "summary": f"以「{topic}」为题材，让{protagonist}在连续危机中追查真相。",
                    "selling_points": ["钩子密集", "节奏清晰", "适合连载"],
                    "risk": "需要控制反转频率，避免过度消耗悬念。" + risk_suffix,
                    "recommended": True,
                },
                {
                    "name": "人物弧光推进",
                    "summary": f"以「{topic}」为题材，把外部事件压进主角的内在选择。",
                    "selling_points": ["人物厚度强", "情绪回报高"],
                    "risk": "前期节奏可能偏慢，需要章节钩子兜底。" + risk_suffix,
                    "recommended": False,
                },
                {
                    "name": "世界规则推进",
                    "summary": f"以「{topic}」为题材，用规则代价制造长期主线压力。",
                    "selling_points": ["设定可扩展", "适合长篇"],
                    "risk": "信息量较大，开篇必须降低理解门槛。" + risk_suffix,
                    "recommended": False,
                },
            ]
        }

    @staticmethod
    def _audit_result() -> dict[str, Any]:
        return {
            "issues": [
                {
                    "issue_type": "continuity",
                    "severity": "medium",
                    "description": "场景结尾出现的关键道具与上一章描述不一致。",
                    "suggested_fix": "在场景中部加一句明确道具属性，再让其在结尾出现。",
                },
                {
                    "issue_type": "character",
                    "severity": "low",
                    "description": "主角在高压下的语气过于冷静，与既定弧光不符。",
                    "suggested_fix": "把主角的关键对白改为更急促的短句。",
                },
            ]
        }

    @staticmethod
    def _chapter_plan(user_prompt: str) -> dict[str, Any]:
        range_match = re.search(r"本次只生成第\s*(\d+)\s*章到第\s*(\d+)\s*章", user_prompt)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
        else:
            target_match = re.search(r"(?:目标章节数|全书目标章节数)：(\d+)", user_prompt)
            start = 1
            end = int(target_match.group(1)) if target_match else 6
        return {
            "chapters": [
                {
                    "chapter_index": index,
                    "title": f"第{index}章 测试转折",
                    "summary": f"第 {index} 章摘要",
                    "goal": "推进主线",
                    "conflict": "目标与阻力碰撞",
                    "ending_hook": "留下下一章钩子",
                }
                for index in range(start, end + 1)
            ]
        }

    @staticmethod
    def _scene_plan(user_prompt: str) -> dict[str, Any]:
        count_match = re.search(r"建议场景数：(\d+)", user_prompt)
        scene_count = int(count_match.group(1)) if count_match else 4
        scene_count = max(1, min(scene_count, 8))
        scenes = []
        for index in range(1, scene_count + 1):
            scenes.append(
                {
                    "scene_index": index,
                    "title": f"测试场景{index}",
                    "time_marker": "承接上一场",
                    "location": "雾城档案馆",
                    "characters": ["林澈"],
                    "scene_purpose": f"推进第 {index} 个章节转折",
                    "entry_state": (
                        "承接上一章悬念" if index == 1 else f"承接场景 {index - 1} 的退场压力"
                    ),
                    "exit_state": (
                        f"留下场景 {index + 1} 必须回应的新压力"
                        if index < scene_count
                        else "形成本章结尾钩子"
                    ),
                    "goal": f"完成场景 {index} 的调查推进",
                    "conflict": "主角目标与监察会阻力碰撞",
                    "must_include": ["承接上一场结果", "推进本章目标"],
                    "must_avoid": ["重复解释已解决的信息", "跳过人物情绪变化"],
                    "emotion_start": "紧张",
                    "emotion_end": "更强的不确定感",
                    "reveal": "新的记忆线索浮出水面",
                    "hook": "下一步选择变得无法回避",
                    "expected_words": 1200,
                }
            )
        return {"chapter_index": 1, "chapter_title": "测试章节", "scenes": scenes}

    @staticmethod
    def _scene_draft() -> dict[str, Any]:
        return {
            "scene_id": "",
            "title": "测试场景",
            "content": (
                "雾笼罩档案馆的清晨，林澈推开门，发现门禁锁芯比昨晚多了一道刻痕。"
                "他蹲下，指尖蹭过冰凉的金属，记忆里浮起一段被篡改过的画面。"
                "妹妹的笑声、关上的门、和那枚他从未真正见过的钥匙同时逼近。"
            ),
            "word_count": 88,
            "continuity_notes": ["已保留场景目标与结尾钩子"],
            "unresolved_threads": [],
        }

    @staticmethod
    def _beat_sheet() -> dict[str, Any]:
        """multi 模式 planner 的伪输出：固定 4 个 beat，覆盖三幕节奏。"""
        return {
            "beats": [
                {
                    "index": 1,
                    "purpose": "开场",
                    "action": "林澈推开档案馆的铁门，雾气先一步钻进室内。",
                    "dialog_hint": "",
                    "reaction": "他握紧手电，耳后微凉。",
                    "target_words": 250,
                },
                {
                    "index": 2,
                    "purpose": "推进",
                    "action": "他扫过门禁锁芯，看到比昨晚多出一道新鲜刻痕。",
                    "dialog_hint": "对自己低声：‘谁先进来过？’",
                    "reaction": "胸口的不安变成清晰的警觉。",
                    "target_words": 300,
                },
                {
                    "index": 3,
                    "purpose": "转折",
                    "action": "他翻出昨日的巡查日志，发现整页登记被人撕去。",
                    "dialog_hint": "",
                    "reaction": "他确认：档案确实被人篡改。",
                    "target_words": 350,
                },
                {
                    "index": 4,
                    "purpose": "结尾钩子",
                    "action": "他在桌沿摸到一枚陌生的金属符号，纹路与妹妹案卷上的印记吻合。",
                    "dialog_hint": "",
                    "reaction": "他把符号塞进口袋，决定追下去。",
                    "target_words": 300,
                },
            ],
            "total_target_words": 1200,
        }

    @staticmethod
    def _character_state_updates(user_prompt: str) -> dict[str, Any]:
        roster: list[dict[str, Any]] = []
        scene: dict[str, Any] = {}
        try:
            roster_text = user_prompt.split("已有人物名册：", 1)[1].split("当前 scene：", 1)[0]
            scene_text = user_prompt.split("当前 scene：", 1)[1]
            roster = json.loads(roster_text.strip())
            scene = json.loads(scene_text.strip())
        except (IndexError, json.JSONDecodeError):
            pass
        scene_names = {str(name) for name in scene.get("characters", [])}
        updates = []
        for character in roster:
            name = str(character.get("name") or "")
            if not name or (scene_names and name not in scene_names):
                continue
            updates.append(
                {
                    "name": name,
                    "current_state": {
                        "last_chapter_index": scene.get("chapter_index"),
                        "last_chapter_title": scene.get("chapter_title"),
                        "last_scene_index": scene.get("scene_index"),
                        "last_scene_title": scene.get("scene_title"),
                        "location": scene.get("location"),
                        "emotional_state": (
                            f"{scene.get('emotion_start')} → {scene.get('emotion_end')}"
                        ),
                        "knowledge_state": scene.get("reveal"),
                        "last_hook": scene.get("hook"),
                    },
                    "relationships": {},
                    "summary": (
                        f"{name}经历了“{scene.get('scene_title') or '当前场景'}”"
                        "的冲突，并获得新信息。"
                    ),
                }
            )
        return {"updates": updates}

    @staticmethod
    def _revision_result() -> dict[str, Any]:
        return {
            "reply": "我建议先强化主题，再补一个可直接落库的人物、世界规则和剧情线。",
            "proposals": [
                {
                    "target_type": "story_bible",
                    "target_id": None,
                    "action": "update",
                    "title": "强化故事主题",
                    "patch": {"theme": "记忆交易背后的代价与自我选择"},
                    "reason": "让故事圣经的核心表达更集中。",
                    "impact": ["characters", "plot_threads"],
                },
                {
                    "target_type": "character",
                    "target_id": None,
                    "action": "create",
                    "title": "新增灰市向导",
                    "patch": {
                        "name": "顾眠",
                        "role": "guide",
                        "description": "熟悉非法记忆样本的灰市向导。",
                        "motivation": "用一次交易换回被夺走的家人记忆。",
                        "arc": "从只求自保到愿意承担代价。",
                    },
                    "reason": "补足主角进入灰市的信息入口。",
                    "impact": ["world_items"],
                },
                {
                    "target_type": "world_item",
                    "target_id": None,
                    "action": "create",
                    "title": "新增硬规则",
                    "patch": {
                        "type": "rule",
                        "name": "记忆等价交换",
                        "description": "任何记忆交易都必须支付同等强度的情绪代价。",
                        "importance": "high",
                        "is_hard_rule": True,
                    },
                    "reason": "让长期冲突有稳定约束。",
                    "impact": ["story_bible"],
                },
                {
                    "target_type": "plot_thread",
                    "target_id": None,
                    "action": "create",
                    "title": "新增灰市支线",
                    "patch": {
                        "title": "灰市记忆样本追查",
                        "thread_type": "side",
                        "description": "主角追踪一批来源不明的非法记忆样本。",
                        "status": "open",
                    },
                    "reason": "提供中段调查推进线。",
                    "impact": ["characters", "world_items"],
                },
            ],
        }

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any]:
        schema_properties = schema.get("properties", {})
        schema_text = str(schema)
        if "proposals" in schema_properties:
            return self._revision_result()
        if "main_characters" in schema_properties:
            return self._story_bible(user_prompt)
        if "chapters" in schema_properties:
            return self._chapter_plan(user_prompt)
        if "scenes" in schema_properties:
            return self._scene_plan(user_prompt)
        if "directions" in schema_properties:
            return self._directions(user_prompt)
        if "issues" in schema_properties:
            return self._audit_result()
        # BeatSheetContract 的特征是 beats + total_target_words，先于 SceneDraftContract 命中
        if "beats" in schema_properties and "total_target_words" in schema_properties:
            return self._beat_sheet()
        if "unresolved_threads" in schema_properties or "SceneDraftContract" in schema_text:
            return self._scene_draft()
        if "updates" in schema_properties:
            return self._character_state_updates(user_prompt)
        return {
            "synthetic": True,
            "model": model,
            "schema_keys": list(schema.keys()),
        }

    async def complete_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        # Sprint 14-C3 multi-agent：drafter / stylist 都通过 complete_text 调用。
        # 用 system_prompt 的提示头特征区分（更稳定，不依赖 user_prompt 措辞）。
        if "场景正文执笔人" in system_prompt or "场景正文执笔" in system_prompt:
            return self._scene_draft_markdown()
        if "场景风格统一器" in system_prompt or "风格统一" in system_prompt:
            return self._scene_stylist_markdown(user_prompt)
        if "正文后处理编辑" in system_prompt:
            return self._postprocess_scene_text(user_prompt)
        return f"[TEST:{model}] 根据上下文生成 scene 级正文（提示约 {len(user_prompt)} 字）。"

    @staticmethod
    def _scene_draft_markdown() -> str:
        """drafter 输出：包含全部 4 个 beat 的 Markdown 草稿。"""
        return (
            "**林澈**推开档案馆的铁门，雾气先一步钻进室内。"
            "他握紧手电，耳后微凉，意识到今天的档案馆并不只是"
            "他熟悉的那个档案馆。\n\n"
            "他蹲下，扫过门禁锁芯——比昨晚多出一道新鲜刻痕。"
            "*‘谁先进来过？’*他对自己低声说，胸口的不安变成清晰的警觉。\n\n"
            "他翻开昨日的巡查日志，整页登记被人撕去。"
            "他确认：档案确实被人篡改。\n\n"
            "在桌沿，他摸到一枚陌生的金属符号，"
            "纹路与妹妹案卷上的印记吻合。"
            "他把符号塞进口袋，决定追下去。"
        )

    @staticmethod
    def _scene_stylist_markdown(user_prompt: str) -> str:
        """stylist 输出：从 user_prompt 中提取 drafter 原文，模拟"轻润色"返回。

        测试不关心润色质量，只关心 model_call 链路；
        因此把 drafter 的输出原样回传即可。
        """
        marker = "## 待润色 Markdown 正文\n"
        if marker in user_prompt:
            tail = user_prompt.split(marker, 1)[1]
            # 去掉后续的"## 任务指令"段
            tail = tail.split("\n\n## 任务指令", 1)[0].strip()
            if tail:
                return tail
        return DeterministicModelProvider._scene_draft_markdown()

    @staticmethod
    def _postprocess_scene_text(user_prompt: str) -> str:
        """后处理输出：抽取原文并移除 Markdown 强调，模拟去 AI 味收口。"""
        marker = "## 待自然化正文\n"
        if marker in user_prompt:
            tail = user_prompt.split(marker, 1)[1]
            tail = tail.split("\n\n## 任务指令", 1)[0].strip()
        else:
            tail = DeterministicModelProvider._scene_draft_markdown()
        tail = re.sub(r"\*\*(.*?)\*\*", r"\1", tail, flags=re.DOTALL)
        tail = re.sub(r"__(.*?)__", r"\1", tail, flags=re.DOTALL)
        tail = re.sub(r"(?<!\*)\*(?!\*)([^*\n]{1,120}?)(?<!\*)\*(?!\*)", r"\1", tail)
        tail = re.sub(r"(?<!_)_(?!_)([^_\n]{1,120}?)(?<!_)_(?!_)", r"\1", tail)
        return tail
