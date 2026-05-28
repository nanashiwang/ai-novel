"""OpenAIChatProvider stream 模式 SSE 解析测试。

不依赖外网；用 httpx.MockTransport 注入伪 SSE 响应，验证 chunks 拼接、
[DONE] 终止、HTTP 错误处理这三条核心路径。
"""
from __future__ import annotations

import httpx
import pytest

from app.services.model_gateway.providers import OpenAIChatProvider


def _sse_body(chunks: list[str], with_done: bool = True) -> bytes:
    """生成 OpenAI 兼容的 SSE 响应体。"""
    import json

    lines = []
    for ch in chunks:
        content_json = json.dumps(ch, ensure_ascii=False)
        payload = (
            f'{{"choices":[{{"delta":{{"content":{content_json}}},"index":0}}]}}'
        )
        lines.append(f"data: {payload}\n")
    if with_done:
        lines.append("data: [DONE]\n")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _make_provider(handler, *, stream: bool = True) -> OpenAIChatProvider:
    """注入 mock transport 的 provider 工厂。

    httpx AsyncClient 的 transport 只能在构造时传入；直接赋值 `_transport`
    不会替换底层连接池。这里通过 monkeypatch `_client()` 返回一个使用
    MockTransport 的全新 client 来达成隔离。
    """
    transport = httpx.MockTransport(handler)
    provider = OpenAIChatProvider(
        api_key="sk-fake",
        base_url="https://nan.meta-api.vip/v1",
        timeout=5.0,
        stream=stream,
    )

    def _client_with_mock() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=provider.base_url,
            timeout=provider.timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            },
        )

    provider._client = _client_with_mock  # type: ignore[method-assign]
    return provider


@pytest.mark.asyncio
async def test_stream_assembles_chunks_into_full_text():
    """SSE 多个 chunk 应按顺序拼成完整字符串。"""

    def handler(request: httpx.Request) -> httpx.Response:
        # 验证 payload 含 stream=true
        import json
        body = json.loads(request.content)
        assert body.get("stream") is True, "stream 模式必须在 payload 显式传 stream=true"
        return httpx.Response(
            200,
            content=_sse_body(["Hello", ", ", "world", "!"]),
            headers={"Content-Type": "text/event-stream"},
        )

    provider = _make_provider(handler)
    text = await provider.complete_text(
        model="gpt-4o-mini",
        system_prompt="sys",
        user_prompt="user",
        temperature=0.0,
    )
    assert text == "Hello, world!"


@pytest.mark.asyncio
async def test_stream_handles_400_by_raising():
    """中转网关返回 400 时应抛 HTTPStatusError 并把 body 带上。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            content=b'{"error":{"message":"Stream must be set to true"}}',
            headers={"Content-Type": "application/json"},
        )

    provider = _make_provider(handler)
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await provider.complete_text(
            model="gpt-4o-mini",
            system_prompt="sys",
            user_prompt="user",
            temperature=0.0,
        )
    # 错误正文应该被携带
    assert "Stream must be set to true" in str(exc.value)


@pytest.mark.asyncio
async def test_stream_retries_transient_503(monkeypatch):
    """中转网关短暂过载时，stream 分支应自动重试。"""

    calls = 0

    async def fake_sleep(_: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                503,
                content=b'{"error":{"code":"system_cpu_overloaded"}}',
                request=request,
            )
        return httpx.Response(
            200,
            content=_sse_body(['{"ok": true}']),
            headers={"Content-Type": "text/event-stream"},
            request=request,
        )

    monkeypatch.setattr("app.services.model_gateway.providers.asyncio.sleep", fake_sleep)
    provider = _make_provider(handler)
    result = await provider.complete_json(
        model="gpt-4o-mini",
        system_prompt="sys",
        user_prompt="user",
        schema={"properties": {"ok": {"type": "boolean"}}},
        temperature=0.0,
    )

    assert result == {"ok": True}
    assert calls == 2


@pytest.mark.asyncio
async def test_stream_ignores_non_data_lines_and_keepalives():
    """SSE 中的 keep-alive 注释行和非 data 行应被忽略。"""

    def handler(request: httpx.Request) -> httpx.Response:
        # 模拟某些中转网关塞 keep-alive 注释、空行、坏 JSON
        body = (
            ": keep-alive\n"
            "\n"
            'data: {"choices":[{"delta":{"content":"片"}}]}\n'
            "data: not-json-garbage\n"  # 坏数据应被忽略
            'data: {"choices":[{"delta":{"content":"段"}}]}\n'
            "data: [DONE]\n"
        )
        return httpx.Response(
            200,
            content=body.encode("utf-8"),
            headers={"Content-Type": "text/event-stream"},
        )

    provider = _make_provider(handler)
    text = await provider.complete_text(
        model="gpt-4o-mini",
        system_prompt="sys",
        user_prompt="user",
        temperature=0.0,
    )
    assert text == "片段"


@pytest.mark.asyncio
async def test_non_stream_mode_still_works():
    """stream=False 默认值应保持原有非流式路径。"""

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(request.content)
        # 非流式分支不应在 payload 里设置 stream
        assert "stream" not in body, "stream=False 时不应传 stream 字段"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "non-stream-OK"}}],
            },
        )

    provider = _make_provider(handler, stream=False)
    text = await provider.complete_text(
        model="gpt-4o-mini",
        system_prompt="sys",
        user_prompt="user",
        temperature=0.0,
    )
    assert text == "non-stream-OK"
