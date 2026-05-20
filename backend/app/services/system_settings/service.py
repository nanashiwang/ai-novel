from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.system_setting import SystemSetting

MODEL_SETTING_KEYS = {
    "provider": "model_gateway.provider",
    "default_model": "model_gateway.default_model",
    "openai_base_url": "model_gateway.openai_base_url",
    "openai_api_key": "model_gateway.openai_api_key",
    "anthropic_base_url": "model_gateway.anthropic_base_url",
    "anthropic_api_key": "model_gateway.anthropic_api_key",
}

SECRET_SETTING_KEYS = {
    MODEL_SETTING_KEYS["openai_api_key"],
    MODEL_SETTING_KEYS["anthropic_api_key"],
}


@dataclass(frozen=True)
class ModelGatewayConfig:
    provider: str
    default_model: str
    openai_base_url: str
    openai_api_key: str
    anthropic_base_url: str
    anthropic_api_key: str

    @property
    def active_base_url(self) -> str:
        if self.provider == "anthropic":
            return self.anthropic_base_url
        return self.openai_base_url

    @property
    def active_api_key(self) -> str:
        if self.provider == "anthropic":
            return self.anthropic_api_key
        return self.openai_api_key


class SystemSettingsService:
    def _defaults(self) -> ModelGatewayConfig:
        settings = get_settings()
        return ModelGatewayConfig(
            provider=settings.model_gateway_provider,
            default_model=settings.default_model,
            openai_base_url=settings.openai_base_url,
            openai_api_key=settings.openai_api_key,
            anthropic_base_url=settings.anthropic_base_url,
            anthropic_api_key=settings.anthropic_api_key,
        )

    async def get_model_config(self, session: AsyncSession) -> ModelGatewayConfig:
        defaults = self._defaults()
        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key.in_(MODEL_SETTING_KEYS.values()))
        )
        values = {row.key: row.value or "" for row in result.scalars().all()}
        return ModelGatewayConfig(
            provider=values.get(MODEL_SETTING_KEYS["provider"], defaults.provider) or "openai",
            default_model=values.get(MODEL_SETTING_KEYS["default_model"], defaults.default_model)
            or "gpt-5.5",
            openai_base_url=values.get(
                MODEL_SETTING_KEYS["openai_base_url"],
                defaults.openai_base_url,
            )
            or "https://api.openai.com/v1",
            openai_api_key=values.get(
                MODEL_SETTING_KEYS["openai_api_key"],
                defaults.openai_api_key,
            ),
            anthropic_base_url=values.get(
                MODEL_SETTING_KEYS["anthropic_base_url"],
                defaults.anthropic_base_url,
            )
            or "https://api.anthropic.com/v1",
            anthropic_api_key=values.get(
                MODEL_SETTING_KEYS["anthropic_api_key"],
                defaults.anthropic_api_key,
            ),
        )

    async def upsert_model_config(
        self,
        session: AsyncSession,
        *,
        provider: str,
        default_model: str,
        openai_base_url: str,
        openai_api_key: str | None,
        anthropic_base_url: str,
        anthropic_api_key: str | None,
    ) -> ModelGatewayConfig:
        current = await self.get_model_config(session)
        values = {
            MODEL_SETTING_KEYS["provider"]: provider,
            MODEL_SETTING_KEYS["default_model"]: default_model,
            MODEL_SETTING_KEYS["openai_base_url"]: openai_base_url,
            MODEL_SETTING_KEYS["openai_api_key"]: (
                openai_api_key if openai_api_key is not None else current.openai_api_key
            ),
            MODEL_SETTING_KEYS["anthropic_base_url"]: anthropic_base_url,
            MODEL_SETTING_KEYS["anthropic_api_key"]: (
                anthropic_api_key if anthropic_api_key is not None else current.anthropic_api_key
            ),
        }

        for key, value in values.items():
            setting = await session.get(SystemSetting, key)
            if setting:
                setting.value = value
                setting.is_secret = key in SECRET_SETTING_KEYS
            else:
                session.add(
                    SystemSetting(
                        key=key,
                        value=value,
                        is_secret=key in SECRET_SETTING_KEYS,
                    )
                )
        await session.flush()
        return await self.get_model_config(session)


system_settings_service = SystemSettingsService()
