from __future__ import annotations

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
            "world_rules": world_rules,
            "main_characters": [
                {
                    "name": protagonist_name,
                    "role": "protagonist",
                    "description": protagonist_desc,
                    "motivation": f"揭开『{topic}』背后被掩盖的真相。",
                    "arc": "从被动卷入到主动承担抉择的代价。",
                },
                {
                    "name": antagonist_name,
                    "role": "antagonist",
                    "description": f"掌控本作核心冲突源头的对立面，{style}下的反派形象。",
                    "motivation": "用自己的方式维护被打破的旧秩序。",
                    "arc": "从秩序维护者滑向掌控一切的人。",
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
        if "main_characters" in schema_properties:
            return self._story_bible(user_prompt)
        if "directions" in schema_properties:
            return self._directions(user_prompt)
        if "issues" in schema_properties:
            return self._audit_result()
        if "unresolved_threads" in schema_properties or "SceneDraftContract" in schema_text:
            return self._scene_draft()
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
        return f"[TEST:{model}] 根据上下文生成 scene 级正文（提示约 {len(user_prompt)} 字）。"
