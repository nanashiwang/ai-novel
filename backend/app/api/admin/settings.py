from __future__ import annotations

import asyncio
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_permission, require_platform_admin
from app.repositories import AuditLogRepository
from app.schemas.common import APIModel
from app.services.model_gateway.providers import (
    AnthropicMessagesProvider,
    OpenAIChatProvider,
)
from app.services.model_gateway.service import model_gateway
from app.services.system_settings import ModelGatewayConfig, system_settings_service

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


class ModelGatewaySettingsResponse(APIModel):
    provider: Literal["openai", "anthropic"]
    default_model: str
    openai_base_url: str
    openai_api_key_configured: bool
    anthropic_base_url: str
    anthropic_api_key_configured: bool
    active_base_url: str
    ready: bool


class ModelGatewaySettingsUpdate(APIModel):
    provider: Literal["openai", "anthropic"] = "openai"
    default_model: str = Field(min_length=1, max_length=120)
    openai_base_url: str = Field(min_length=1, max_length=500)
    openai_api_key: str | None = Field(default=None, max_length=4000)
    anthropic_base_url: str = Field(min_length=1, max_length=500)
    anthropic_api_key: str | None = Field(default=None, max_length=4000)

    @field_validator("openai_api_key", "anthropic_api_key")
    @classmethod
    def blank_secret_means_keep(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("default_model", "openai_base_url", "anthropic_base_url")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("required")
        return stripped


def _to_response(config: ModelGatewayConfig) -> ModelGatewaySettingsResponse:
    active_key = config.active_api_key
    return ModelGatewaySettingsResponse(
        provider=config.provider if config.provider in {"openai", "anthropic"} else "openai",
        default_model=config.default_model,
        openai_base_url=config.openai_base_url,
        openai_api_key_configured=bool(config.openai_api_key),
        anthropic_base_url=config.anthropic_base_url,
        anthropic_api_key_configured=bool(config.anthropic_api_key),
        active_base_url=config.active_base_url,
        ready=bool(active_key),
    )


@router.get("/model-gateway", response_model=ModelGatewaySettingsResponse)
async def get_model_gateway_settings(user: CurrentUserDep, db: DbDep):
    require_platform_admin(user)
    config = await system_settings_service.get_model_config(db)
    return _to_response(config)


@router.put("/model-gateway", response_model=ModelGatewaySettingsResponse)
async def update_model_gateway_settings(
    payload: ModelGatewaySettingsUpdate,
    user: CurrentUserDep,
    db: DbDep,
):
    require_permission(user, "admin:system:update")

    # 记录变更前的配置（不含敏感字段），用于审计 before/after 对比
    before = await system_settings_service.get_model_config(db)
    before_snapshot = {
        "provider": before.provider,
        "default_model": before.default_model,
        "openai_base_url": before.openai_base_url,
        "anthropic_base_url": before.anthropic_base_url,
        "openai_api_key_configured": bool(before.openai_api_key),
        "anthropic_api_key_configured": bool(before.anthropic_api_key),
    }

    config = await system_settings_service.upsert_model_config(
        db,
        provider=payload.provider,
        default_model=payload.default_model,
        openai_base_url=payload.openai_base_url,
        openai_api_key=payload.openai_api_key,
        anthropic_base_url=payload.anthropic_base_url,
        anthropic_api_key=payload.anthropic_api_key,
    )
    if not config.active_api_key:
        raise HTTPException(status_code=400, detail="active_provider_api_key_required")
    model_gateway.configure(config)

    after_snapshot = {
        "provider": config.provider,
        "default_model": config.default_model,
        "openai_base_url": config.openai_base_url,
        "anthropic_base_url": config.anthropic_base_url,
        "openai_api_key_configured": bool(config.openai_api_key),
        "anthropic_api_key_configured": bool(config.anthropic_api_key),
    }
    # 写 audit_logs：actor / target / before / after，敏感字段（api_key 全文）
    # 不进入 before/after，避免审计表泄露密钥；仅记录"是否配置"布尔位。
    # admin/settings 是平台级配置，organization_id 用 actor 用户的当前 org
    # 上下文，没有时回落到 "platform" sentinel。
    await AuditLogRepository(db).create(
        organization_id=user.preferred_organization_id or "platform",
        actor_user_id=user.id,
        action="model_gateway:update",
        target_type="system_setting",
        target_id="model-gateway",
        before_data=before_snapshot,
        after_data=after_snapshot,
    )

    await db.commit()
    return _to_response(config)


# --- 连接测试 ---


class ModelGatewayTestRequest(APIModel):
    """测试入参，全部可选；任一字段缺失时回落到 db 里现存配置。

    用法：admin 在保存配置之前用「测试连接」按钮预先验证，避免保存了错
    配置反而把生产生成链路弄崩。
    """

    provider: Literal["openai", "anthropic"] | None = None
    default_model: str | None = Field(default=None, max_length=120)
    openai_base_url: str | None = Field(default=None, max_length=500)
    openai_api_key: str | None = Field(default=None, max_length=4000)
    anthropic_base_url: str | None = Field(default=None, max_length=500)
    anthropic_api_key: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "default_model",
        "openai_base_url",
        "openai_api_key",
        "anthropic_base_url",
        "anthropic_api_key",
    )
    @classmethod
    def strip_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ModelGatewayTestResponse(APIModel):
    ok: bool
    provider: str
    default_model: str
    base_url: str
    latency_ms: int
    sample: str = ""
    error: str = ""


@router.post(
    "/model-gateway/test",
    response_model=ModelGatewayTestResponse,
)
async def test_model_gateway(
    payload: ModelGatewayTestRequest,
    user: CurrentUserDep,
    db: DbDep,
):
    """连接测试：用当前页面草稿（或 db 现有配置）实例化 provider，
    发一个极短 prompt 验证 URL / Key 是否正确。

    设计要点：
    - 不写 model_calls 表（避免审计噪音）
    - 不扣 quota
    - 不修改 model_gateway 单例（不影响后续真实任务）
    - timeout 限 15s，失败也快速返回让 UI 显示错误
    """
    require_permission(user, "admin:system:update")

    existing = await system_settings_service.get_model_config(db)
    provider_name = payload.provider or existing.provider or "openai"
    default_model = payload.default_model or existing.default_model

    if provider_name == "anthropic":
        base_url = payload.anthropic_base_url or existing.anthropic_base_url
        api_key = payload.anthropic_api_key or existing.anthropic_api_key
    else:
        base_url = payload.openai_base_url or existing.openai_base_url
        api_key = payload.openai_api_key or existing.openai_api_key

    if not api_key:
        return ModelGatewayTestResponse(
            ok=False,
            provider=provider_name,
            default_model=default_model,
            base_url=base_url,
            latency_ms=0,
            error="missing_api_key",
        )

    # 临时实例化 provider，timeout 收紧到 15s 避免阻塞 UI
    if provider_name == "anthropic":
        provider = AnthropicMessagesProvider(
            api_key=api_key,
            base_url=base_url,
            timeout=15.0,
        )
    else:
        provider = OpenAIChatProvider(
            api_key=api_key,
            base_url=base_url,
            timeout=15.0,
            # 测试连接默认走 stream，兼容强制要求 stream=true 的中转网关
            # （如 nan.meta-api.vip / xx.api2d.net 等）。OpenAI 官方也兼容。
            stream=True,
        )

    started = time.perf_counter()
    try:
        text = await asyncio.wait_for(
            provider.complete_text(
                model=default_model,
                system_prompt="You are a connection test bot. Reply with exactly: OK",
                user_prompt="ping",
                temperature=0.0,
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        return ModelGatewayTestResponse(
            ok=False,
            provider=provider_name,
            default_model=default_model,
            base_url=base_url,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error="timeout_15s",
        )
    except Exception as exc:  # noqa: BLE001
        return ModelGatewayTestResponse(
            ok=False,
            provider=provider_name,
            default_model=default_model,
            base_url=base_url,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc)[:500],
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    return ModelGatewayTestResponse(
        ok=True,
        provider=provider_name,
        default_model=default_model,
        base_url=base_url,
        latency_ms=latency_ms,
        sample=(text or "").strip()[:200],
    )
