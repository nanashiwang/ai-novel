"""模型网关。

生产链路只调用真实模型 provider；测试替身只存在于 tests 中。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.common import new_id
from app.models.model_call import ModelCall
from app.services.model_gateway.providers import AnthropicMessagesProvider, OpenAIChatProvider
from app.services.system_settings import ModelGatewayConfig, system_settings_service

_logger = logging.getLogger(__name__)


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



class _RealProviderPlaceholder:
    """真实 provider 占位：触发时显式报错，提示部署方注入实际实现。"""

    async def complete_json(self, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
        raise NotImplementedError(
            "真实模型 provider 未配置。请在启动脚本中调用 "
            "model_gateway.set_provider(...) 设置 OpenAI/Anthropic/自托管 client。"
        )

    async def complete_text(self, **kwargs: Any) -> str:  # noqa: ANN401
        raise NotImplementedError(
            "真实模型 provider 未配置。"
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
        self._provider: ModelProvider = _RealProviderPlaceholder()
        self._settings_cache_at: float = 0.0  # monotonic 时间；0 = 强制首次刷新

    def set_provider(self, provider: ModelProvider) -> None:
        """部署时注入真实 provider。"""
        self._provider = provider

    def configure(self, config: ModelGatewayConfig) -> None:
        self._default_model = config.default_model
        if config.provider == "openai" and config.openai_api_key:
            self._provider = OpenAIChatProvider(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
                timeout=self.settings.model_gateway_timeout_seconds,
                # 中转网关强制 stream=true；OpenAI 官方亦兼容
                stream=True,
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
        try:
            response_json = await self._provider.complete_json(
                model=self._default_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                temperature=temperature,
            )
        except Exception as exc:
            await self._record_failed_call_best_effort(
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                task_type=task_type,
                prompt_key=prompt_key or task_type,
                prompt_version=prompt_version,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_json=None,
                response_text=None,
                started=started,
                status="failed",
                error_message=str(exc),
            )
            raise
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
            metadata=metadata,
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
        try:
            response_text = await self._provider.complete_text(
                model=self._default_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
            )
        except Exception as exc:
            await self._record_failed_call_best_effort(
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                task_type=task_type,
                prompt_key=prompt_key or task_type,
                prompt_version=prompt_version,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_json=None,
                response_text=None,
                started=started,
                status="failed",
                error_message=str(exc),
            )
            raise
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
            metadata=metadata,
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
        status: str = "success",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
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

        MODEL_CALL_LATENCY.labels(task_type=task_type, status=status).observe(latency_ms)
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
            status=status,
            error_message=error_message,
            metadata_json=dict(metadata) if metadata else None,
        )
        session.add(call)
        await session.flush()

    async def _record_failed_call_best_effort(
        self,
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
        status: str,
        error_message: str,
    ) -> None:
        try:
            from app.core.database import AsyncSessionLocal  # noqa: PLC0415

            async with AsyncSessionLocal() as audit_session:
                await self._record_call(
                    audit_session,
                    organization_id=organization_id,
                    project_id=project_id,
                    job_id=job_id,
                    task_type=task_type,
                    prompt_key=prompt_key,
                    prompt_version=prompt_version,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_json=response_json,
                    response_text=response_text,
                    started=started,
                    status=status,
                    error_message=error_message,
                )
                await audit_session.commit()
        except Exception:  # noqa: BLE001
            _logger.exception(
                "failed_to_record_model_call_failure",
                extra={"job_id": job_id, "task_type": task_type},
            )


model_gateway = ModelGateway()
