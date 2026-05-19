import httpx
import pytest

from app.services.model_gateway import providers
from app.services.model_gateway.providers import OpenAIChatProvider


@pytest.mark.asyncio
async def test_openai_provider_retries_transient_gateway_errors(monkeypatch):
    calls = 0

    async def fake_sleep(_: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(502, text="bad gateway", request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
            request=request,
        )

    provider = OpenAIChatProvider(api_key="test", base_url="https://proxy.example/v1")
    monkeypatch.setattr(providers.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.AsyncClient(
            base_url=provider.base_url,
            transport=httpx.MockTransport(handler),
        ),
    )

    result = await provider.complete_json(
        model="test-model",
        system_prompt="system",
        user_prompt="user",
        schema={"properties": {"ok": {"type": "boolean"}}},
        temperature=0,
    )

    assert result == {"ok": True}
    assert calls == 2
