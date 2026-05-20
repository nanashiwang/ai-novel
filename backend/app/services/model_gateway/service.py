"""模型网关。

- MODEL_GATEWAY_MODE=mock：返回 mock 数据并落库 model_calls
- MODEL_GATEWAY_MODE=real：通过可插拔 provider 调用真实模型；
  当前内置 provider 为占位（raise NotImplementedError），便于在不同部署环境
  通过 monkey-patch 注入 OpenAI / Anthropic / 自托管模型客户端。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.common import new_id
from app.models.model_call import ModelCall
from app.services.model_gateway.providers import AnthropicMessagesProvider, OpenAIChatProvider
from app.services.system_settings import ModelGatewayConfig, system_settings_service


def _estimate_tokens(text: str) -> int:
    """粗略 token 估算：CJK 字符 1 char/token，其他 1 token/4 char。

    项目以中文长篇小说为主，统一 `len // 4` 的英文比例会显著低估输入 tokens、
    高估剩余预算。Sprint 1 阶段先用启发式区分 CJK/non-CJK，真实计量交由
    provider 的 usage 字段（接入真实 provider 后切换）。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, cjk + other // 4)


class ModelProvider(Protocol):
    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any]: ...

    async def complete_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str: ...


class _MockProvider:
    """开发用：返回结构化但确定性的内容，避免烧 token。

    Story Bible 路径下会从 user_prompt 中解析出项目标题 / 类型 / 主角原型 /
    禁忌主题等字段，按字段动态拼出 fixture——不同项目得到不同人物名、
    premise 描述与世界规则，避免"每个项目长得一样"的体验问题。
    """

    @staticmethod
    def _parse_prompt_fields(user_prompt: str) -> dict[str, Any]:
        """从 novel_planner 拼装的 user_prompt 里反解关键字段。

        novel_planner 用固定模板 `xxx：value` 输出，因此可以直接抓"中文冒号
        + 后续到换行"的内容。失败时返回空字符串，让上层取兜底值。
        """
        patterns = {
            "title": r"项目标题：([^\n]*)",
            "genre": r"类型：([^\n]*)",
            "target_reader": r"目标读者：([^\n]*)",
            "style": r"文风：([^\n]*)",
            "topic": r"初始题材/topic：([^\n]*)",
            "protagonist": r"主角原型/期望：([^\n]*)",
            "references": r"参考作品[^\n]*：([^\n]*)",
            "forbidden": r"禁忌主题[^\n]*：([^\n]*)",
        }
        out: dict[str, Any] = {}
        for key, pat in patterns.items():
            m = re.search(pat, user_prompt)
            out[key] = (m.group(1).strip() if m else "")
        return out

    @staticmethod
    def _seed_int(text: str) -> int:
        """用 title 做稳定 hash，让同一项目每次 mock 结果一致，方便测试。"""
        seed = 0
        for ch in text:
            seed = (seed * 131 + ord(ch)) & 0xFFFFFFFF
        return seed

    def _mock_story_bible(self, user_prompt: str) -> dict[str, Any]:
        fields = self._parse_prompt_fields(user_prompt)
        title = fields.get("title") or "未命名小说"
        genre = fields.get("genre") or "悬疑幻想"
        style = fields.get("style") or "画面清晰、冲突明确"
        target_reader = fields.get("target_reader") or "中文长篇类型小说读者"
        topic = fields.get("topic") or title
        protagonist = fields.get("protagonist") or ""
        forbidden = fields.get("forbidden") or ""

        # 用 title 做种子在 3 套人物名 / 3 套世界规则模板间选择，
        # 不同项目得到不同基线
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

        protagonist_desc = (
            protagonist or f"在『{title}』中追逐真相的核心角色，专长契合本作题材。"
        )

        constraints = ["保持世界规则前后一致", "避免无铺垫反转"]
        if forbidden:
            constraints.append(f"严禁出现：{forbidden}")

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

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any]:
        if "StoryBibleContract" in str(schema) or "main_characters" in schema.get("properties", {}):
            return self._mock_story_bible(user_prompt)
        schema_str = str(schema)
        # AuditResultContract: 含 issues 数组的 schema
        if "AuditIssueItem" in schema_str or (
            "issues" in schema.get("properties", {})
            and "premise" not in schema.get("properties", {})
        ):
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
                        "description": "主角在高压下的语气过于冷静，与设定的'急于求成'弧光不符。",
                        "suggested_fix": "把主角的关键对白改为更急促的短句。",
                    },
                ]
            }
        # SceneDraftContract: 含 scene_id + content
        if "SceneDraftContract" in schema_str or "unresolved_threads" in schema.get(
            "properties", {}
        ):
            return {
                "scene_id": "",
                "title": "Mock 重写场景",
                "content": (
                    "雾笼罩档案馆的清晨，林澈推开门，发现门禁锁芯比昨晚多了一道刻痕。"
                    "他蹲下，指尖蹭过冰凉的金属，记忆里浮起一段被篡改过的画面——"
                    "妹妹的笑声、关上的门、和那枚他从未真正见过的钥匙。"
                    "（Mock 重写正文：已基于待修复问题润色，保留原场景目标与钩子。）"
                ),
                "word_count": 96,
                "continuity_notes": ["mock 重写：已按 issues 修订关键道具描述"],
                "unresolved_threads": [],
            }
        return {
            "mock": True,
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
        return f"[MOCK:{model}] 根据上下文生成 scene 级正文（提示约 {len(user_prompt)} 字）。"


class _RealProviderPlaceholder:
    """真实 provider 占位：触发时显式报错，提示部署方注入实际实现。"""

    async def complete_json(self, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
        raise NotImplementedError(
            "MODEL_GATEWAY_MODE=real 但未注入 provider。请在启动脚本中调用 "
            "model_gateway.set_provider(...) 设置 OpenAI/Anthropic/自托管 client。"
        )

    async def complete_text(self, **kwargs: Any) -> str:  # noqa: ANN401
        raise NotImplementedError(
            "MODEL_GATEWAY_MODE=real 但未注入 provider。"
        )


class ModelGateway:
    # system_settings 缓存 TTL（秒）。过短会让密集生成场景每次都查库；过长则
    # 管理员通过 admin API 修改设置后的生效延迟变长。admin 修改路径会调用
    # configure() 立即覆盖缓存时间戳，30 秒上限只影响"绕过 admin API 直接
    # 改 system_settings 表"的边界场景。
    _SETTINGS_CACHE_TTL_SECONDS = 30.0

    def __init__(self) -> None:
        self.settings = get_settings()
        self._default_model = self.settings.default_model
        self._provider: ModelProvider = (
            _MockProvider()
            if self.settings.model_gateway_mode == "mock"
            else _RealProviderPlaceholder()
        )
        self._settings_cache_at: float = 0.0  # monotonic 时间；0 = 强制首次刷新

    def set_provider(self, provider: ModelProvider) -> None:
        """部署时注入真实 provider。"""
        self._provider = provider

    def configure(self, config: ModelGatewayConfig) -> None:
        self._default_model = config.default_model
        if config.mode != "real":
            self._provider = _MockProvider()
        elif config.provider == "openai" and config.openai_api_key:
            self._provider = OpenAIChatProvider(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
                timeout=self.settings.model_gateway_timeout_seconds,
            )
        elif config.provider == "anthropic" and config.anthropic_api_key:
            self._provider = AnthropicMessagesProvider(
                api_key=config.anthropic_api_key,
                base_url=config.anthropic_base_url,
                timeout=self.settings.model_gateway_timeout_seconds,
            )
        else:
            self._provider = _RealProviderPlaceholder()
        # admin 改设置或启动注入后视为缓存已是最新，避免下一次生成立刻又查库。
        self._settings_cache_at = time.monotonic()

    def invalidate_settings_cache(self) -> None:
        """让下一次 refresh_from_settings 强制查库。"""
        self._settings_cache_at = 0.0

    async def refresh_from_settings(self, session: AsyncSession, *, force: bool = False) -> None:
        if not force:
            elapsed = time.monotonic() - self._settings_cache_at
            if elapsed < self._SETTINGS_CACHE_TTL_SECONDS:
                return
        config = await system_settings_service.get_model_config(session)
        self.configure(config)

    async def generate_json(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str | None,
        job_id: str | None,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        prompt_key: str | None = None,
        prompt_version: str = "v1",
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self.refresh_from_settings(session)
        started = time.perf_counter()
        response_json = await self._provider.complete_json(
            model=self._default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
            temperature=temperature,
        )
        await self._record_call(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type=task_type,
            prompt_key=prompt_key or task_type,
            prompt_version=prompt_version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_json=response_json,
            response_text=None,
            started=started,
        )
        return response_json

    async def generate_text(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str | None,
        job_id: str | None,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        prompt_key: str | None = None,
        prompt_version: str = "v1",
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        await self.refresh_from_settings(session)
        started = time.perf_counter()
        response_text = await self._provider.complete_text(
            model=self._default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
        await self._record_call(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type=task_type,
            prompt_key=prompt_key or task_type,
            prompt_version=prompt_version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_json=None,
            response_text=response_text,
            started=started,
        )
        return response_text

    async def _record_call(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str | None,
        job_id: str | None,
        task_type: str,
        prompt_key: str,
        prompt_version: str,
        system_prompt: str,
        user_prompt: str,
        response_json: dict[str, Any] | None,
        response_text: str | None,
        started: float,
    ) -> None:
        input_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt)
        input_tokens = max(1, input_tokens)
        output_tokens = max(
            1,
            _estimate_tokens(response_text or json.dumps(response_json or {}, ensure_ascii=False)),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        # Prometheus 埋点：模型调用延迟（按 task_type / 成功状态）
        from app.core.metrics import MODEL_CALL_LATENCY  # noqa: PLC0415

        MODEL_CALL_LATENCY.labels(task_type=task_type, status="success").observe(
            latency_ms
        )
        call = ModelCall(
            id=new_id("model_call"),
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type=task_type,
            model=self._default_model,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            response_json=response_json,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            status="success",
        )
        session.add(call)
        await session.flush()


model_gateway = ModelGateway()
