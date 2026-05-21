"""Moderation 服务测试（Sprint 13-A3）。

覆盖本地规则的命中/未命中、severity 升级、provider 字段。OpenAI provider
不在单测里调用真实 API；通过 monkeypatch 验证集成路径即可。
"""
from __future__ import annotations

import pytest

from app.services.moderation import ModerationResult, moderation_service


@pytest.mark.asyncio
async def test_clean_text_returns_none():
    res = await moderation_service.check("主角走进了一座灯火辉煌的城市，呼吸着秋天的空气。")
    assert res.flagged is False
    assert res.categories == []
    assert res.severity == "none"


@pytest.mark.asyncio
async def test_violence_flagged_medium():
    res = await moderation_service.check("他举起斧头，一刀砍杀了那个人。")
    assert res.flagged is True
    assert "violence" in res.categories
    assert res.severity in ("medium", "high")
    assert res.provider == "local"


@pytest.mark.asyncio
async def test_self_harm_high_severity():
    res = await moderation_service.check("文章详细介绍如何自残，包含具体步骤。")
    assert res.flagged is True
    assert "self_harm" in res.categories
    assert res.severity == "high"


@pytest.mark.asyncio
async def test_multiple_categories_take_max_severity():
    res = await moderation_service.check(
        "前面砍杀了一个人，后面又给出了上吊步骤。"
    )
    assert res.flagged is True
    assert {"violence", "self_harm"}.issubset(set(res.categories))
    assert res.severity == "high"


@pytest.mark.asyncio
async def test_empty_text_short_circuit():
    res = await moderation_service.check("")
    assert res.flagged is False


@pytest.mark.asyncio
async def test_disabled_via_settings(monkeypatch):
    from app.core import config as config_module
    from app.services.moderation import service as mod_service

    original = config_module.get_settings()

    class _DisabledSettings:
        moderation_enabled = False
        moderation_provider = "local"
        openai_api_key = ""
        openai_base_url = original.openai_base_url

    monkeypatch.setattr(mod_service, "get_settings", lambda: _DisabledSettings())
    res = await moderation_service.check("文章详细介绍如何自残。")
    assert res.flagged is False


def test_moderation_result_is_immutable():
    from dataclasses import FrozenInstanceError

    res = ModerationResult(flagged=False)
    with pytest.raises(FrozenInstanceError):
        res.flagged = True  # type: ignore[misc]
