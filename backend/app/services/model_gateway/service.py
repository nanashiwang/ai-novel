"""模型网关。

- MODEL_GATEWAY_MODE=mock：返回 mock 数据并落库 model_calls
- MODEL_GATEWAY_MODE=real：通过可插拔 provider 调用真实模型；
  当前内置 provider 为占位（raise NotImplementedError），便于在不同部署环境
  通过 monkey-patch 注入 OpenAI / Anthropic / 自托管模型客户端。
"""
from __future__ import annotations

import json
import time
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.common import new_id
from app.models.model_call import ModelCall
from app.services.model_gateway.providers import AnthropicMessagesProvider, OpenAIChatProvider
from app.services.system_settings import ModelGatewayConfig, system_settings_service


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
    """开发用：返回结构化但确定性的内容，避免烧 token。"""

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
            return {
                "premise": "一名创作者在失控的记忆城市中追查真相。",
                "theme": "记忆、选择与自我救赎",
                "genre": "悬疑幻想",
                "tone": "冷峻、克制、逐步升温",
                "target_reader": "中文长篇类型小说读者",
                "narrative_pov": "第三人称有限视角",
                "style_guide": "画面清晰，冲突明确，每章保留悬念钩子。",
                "constraints": ["保持世界规则前后一致", "避免无铺垫反转"],
                "world_rules": ["记忆可以被交易，但会留下情绪残影", "城市档案馆记录每一次被篡改的过去"],
                "main_characters": [
                    {
                        "name": "林澈",
                        "role": "protagonist",
                        "description": "失去部分记忆的档案修复师。",
                        "motivation": "找回妹妹失踪当晚的真相。",
                        "arc": "从逃避过去到主动承担真相代价。",
                    },
                    {
                        "name": "沈砚",
                        "role": "antagonist",
                        "description": "掌控地下记忆交易的前调查员。",
                        "motivation": "用篡改记忆阻止更大的灾难。",
                        "arc": "从秩序维护者滑向控制一切的人。",
                    },
                ],
                "continuity_rules": ["林澈不能直接想起核心真相", "记忆交易必须付出等价情绪代价"],
                "plot_threads": ["妹妹失踪案", "地下记忆交易网络", "档案馆隐藏的城市原罪"],
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
    def __init__(self) -> None:
        self.settings = get_settings()
        self._default_model = self.settings.default_model
        self._provider: ModelProvider = (
            _MockProvider() if self.settings.model_gateway_mode == "mock" else _RealProviderPlaceholder()
        )

    def set_provider(self, provider: ModelProvider) -> None:
        """部署时注入真实 provider。"""
        self._provider = provider

    def configure(self, config: ModelGatewayConfig) -> None:
        self._default_model = config.default_model
        if config.mode != "real":
            self._provider = _MockProvider()
            return
        if config.provider == "openai" and config.openai_api_key:
            self._provider = OpenAIChatProvider(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
            )
            return
        if config.provider == "anthropic" and config.anthropic_api_key:
            self._provider = AnthropicMessagesProvider(
                api_key=config.anthropic_api_key,
                base_url=config.anthropic_base_url,
            )
            return
        self._provider = _RealProviderPlaceholder()

    async def refresh_from_settings(self, session: AsyncSession) -> None:
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
        system_prompt: str,
        user_prompt: str,
        response_json: dict[str, Any] | None,
        response_text: str | None,
        started: float,
    ) -> None:
        input_tokens = max(1, (len(system_prompt) + len(user_prompt)) // 4)
        output_tokens = max(1, len(response_text or json.dumps(response_json or {})) // 4)
        call = ModelCall(
            id=new_id("model_call"),
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type=task_type,
            model=self._default_model,
            prompt_key=task_type,
            prompt_version="v1",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            response_json=response_json,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status="success",
        )
        session.add(call)
        await session.flush()


model_gateway = ModelGateway()
