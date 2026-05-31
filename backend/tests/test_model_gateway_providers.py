import httpx
import pytest

from app.services.model_gateway import providers
from app.services.model_gateway.providers import OpenAIChatProvider
from app.services.model_gateway.service import _format_exception_for_record


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


@pytest.mark.asyncio
async def test_openai_provider_retries_connect_errors(monkeypatch):
    calls = 0

    async def fake_sleep(_: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("", request=request)
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


def test_format_exception_for_record_keeps_empty_exception_type():
    assert _format_exception_for_record(httpx.ConnectError("")) == "ConnectError"


@pytest.mark.asyncio
async def test_openai_provider_repairs_invalid_json_once():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = '{"items": ["broken" "json"]}' if calls == 1 else '{"items": ["fixed"]}'
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
            request=request,
        )

    provider = OpenAIChatProvider(api_key="test", base_url="https://proxy.example/v1")
    provider._client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        base_url=provider.base_url,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.complete_json(
        model="test-model",
        system_prompt="system",
        user_prompt="user",
        schema={"properties": {"items": {"type": "array"}}},
        temperature=0.7,
    )

    assert result == {"items": ["fixed"]}
    assert calls == 2
