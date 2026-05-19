from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from app.api.deps import CurrentUserDep, DbDep
from app.core.permissions import require_permission, require_platform_admin
from app.repositories import AuditLogRepository
from app.schemas.common import APIModel
from app.services.model_gateway.service import model_gateway
from app.services.system_settings import ModelGatewayConfig, system_settings_service

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


class ModelGatewaySettingsResponse(APIModel):
    mode: Literal["mock", "real"]
    provider: Literal["openai", "anthropic"]
    default_model: str
    openai_base_url: str
    openai_api_key_configured: bool
    anthropic_base_url: str
    anthropic_api_key_configured: bool
    active_base_url: str
    ready: bool


class ModelGatewaySettingsUpdate(APIModel):
    mode: Literal["mock", "real"] = "mock"
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
        mode=config.mode if config.mode in {"mock", "real"} else "mock",
        provider=config.provider if config.provider in {"openai", "anthropic"} else "openai",
        default_model=config.default_model,
        openai_base_url=config.openai_base_url,
        openai_api_key_configured=bool(config.openai_api_key),
        anthropic_base_url=config.anthropic_base_url,
        anthropic_api_key_configured=bool(config.anthropic_api_key),
        active_base_url=config.active_base_url,
        ready=config.mode == "mock" or bool(active_key),
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
        "mode": before.mode,
        "provider": before.provider,
        "default_model": before.default_model,
        "openai_base_url": before.openai_base_url,
        "anthropic_base_url": before.anthropic_base_url,
        "openai_api_key_configured": bool(before.openai_api_key),
        "anthropic_api_key_configured": bool(before.anthropic_api_key),
    }

    config = await system_settings_service.upsert_model_config(
        db,
        mode=payload.mode,
        provider=payload.provider,
        default_model=payload.default_model,
        openai_base_url=payload.openai_base_url,
        openai_api_key=payload.openai_api_key,
        anthropic_base_url=payload.anthropic_base_url,
        anthropic_api_key=payload.anthropic_api_key,
    )
    if config.mode == "real" and not config.active_api_key:
        raise HTTPException(status_code=400, detail="active_provider_api_key_required")
    model_gateway.configure(config)

    after_snapshot = {
        "mode": config.mode,
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

