"""模型网关连接测试 endpoint。

测试只覆盖"业务路径"——不真的发 HTTP 出去（避免单测依赖外网）。
真实 LLM 调用由 monkeypatch provider 模拟。
"""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> str:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_model_gateway_test_missing_key_returns_ok_false(client):
    """没有 api_key 也不应该报 500；ok=false + error=missing_api_key。"""
    token = await _register(client, "gateway-test-1@example.com")
    res = await client.post(
        "/api/v1/admin/settings/model-gateway/test",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "openai"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["error"] == "missing_api_key"


@pytest.mark.asyncio
async def test_model_gateway_test_succeeds_when_provider_returns(client, monkeypatch):
    """用 monkeypatch 注入一个总返回 OK 的 provider，验证 happy path。"""
    token = await _register(client, "gateway-test-2@example.com")

    # monkeypatch OpenAIChatProvider.complete_text 直接返回 "OK"
    async def fake_complete_text(self, **kwargs):  # noqa: ANN001
        return "OK"

    from app.services.model_gateway import providers as p

    monkeypatch.setattr(p.OpenAIChatProvider, "complete_text", fake_complete_text)

    res = await client.post(
        "/api/v1/admin/settings/model-gateway/test",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider": "openai",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_api_key": "sk-test-fake",
            "default_model": "gpt-4o-mini",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["sample"] == "OK"
    assert body["base_url"] == "https://api.openai.com/v1"
    assert body["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_model_gateway_test_captures_provider_exception(client, monkeypatch):
    """provider 抛错时返回 ok=false + error 文本（不是 500）。"""
    token = await _register(client, "gateway-test-3@example.com")

    async def boom(self, **kwargs):  # noqa: ANN001
        raise RuntimeError("invalid api key")

    from app.services.model_gateway import providers as p

    monkeypatch.setattr(p.OpenAIChatProvider, "complete_text", boom)

    res = await client.post(
        "/api/v1/admin/settings/model-gateway/test",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider": "openai",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_api_key": "sk-bad",
            "default_model": "gpt-4o-mini",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "invalid api key" in body["error"]


@pytest.mark.asyncio
async def test_model_gateway_test_anthropic_branch(client, monkeypatch):
    """provider=anthropic 时走 AnthropicMessagesProvider。"""
    token = await _register(client, "gateway-test-4@example.com")

    async def fake_complete_text(self, **kwargs):  # noqa: ANN001
        return "OK from anthropic"

    from app.services.model_gateway import providers as p

    monkeypatch.setattr(p.AnthropicMessagesProvider, "complete_text", fake_complete_text)

    res = await client.post(
        "/api/v1/admin/settings/model-gateway/test",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider": "anthropic",
            "anthropic_base_url": "https://api.anthropic.com/v1",
            "anthropic_api_key": "sk-ant-fake",
            "default_model": "claude-3-5-sonnet",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["provider"] == "anthropic"
    assert "anthropic" in body["sample"].lower()


@pytest.mark.asyncio
async def test_model_gateway_test_requires_super_admin(client):
    """普通用户应 403。"""
    await _register(client, "gateway-first@example.com")  # 占用 super_admin
    token = await _register(client, "gateway-normal@example.com")
    res = await client.post(
        "/api/v1/admin/settings/model-gateway/test",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "openai"},
    )
    assert res.status_code == 403
