"""可插拔的 Model Provider。

约定：
- complete_text：返回纯文本
- complete_json：要求模型按 schema 返回 JSON，调用方负责 schema 约束

OpenAI / Anthropic 都通过 HTTP client 调用，避免强依赖 SDK；
真实部署可通过 `model_gateway.set_provider(...)` 注入自实现 client。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _raise_for_status(response: httpx.Response) -> None:
    """保留上游错误正文，方便从日志判断是模型、参数还是网关问题。"""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:1000]
        raise httpx.HTTPStatusError(
            f"{exc} response_body={body}",
            request=exc.request,
            response=exc.response,
        ) from exc


async def _post_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    payload: dict[str, Any],
    timeout_seconds: float,
    attempts: int = 2,
) -> httpx.Response:
    last_timeout: httpx.TimeoutException | None = None
    for attempt in range(max(1, attempts)):
        try:
            response = await client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            last_timeout = exc
            if attempt >= attempts - 1:
                break
        else:
            if (
                response.status_code not in _TRANSIENT_STATUS_CODES
                or attempt >= attempts - 1
            ):
                return response
        await asyncio.sleep(min(2**attempt, 5))
    raise TimeoutError(f"model_gateway_timeout_after_{timeout_seconds:g}s") from last_timeout


async def _stream_chat_completion(
    client: httpx.AsyncClient,
    path: str,
    *,
    payload: dict[str, Any],
) -> str:
    """以 SSE 方式调用 OpenAI 兼容的 /chat/completions 并拼出完整文本。

    很多 OpenAI 中转网关（如 nan.meta-api.vip）**强制要求 stream=true**，
    非流式请求会被 400 拒。此处保证 payload 必带 stream=true，并把
    `choices[0].delta.content` 拼成完整 text 返回，对调用方透明。

    错误处理：
    - 4xx/5xx 不会自动 raise（httpx stream 模式特性），手动读 body 抛错；
    - 上游中途断流：当前实现以"已经收到的片段"作为结果返回，但若没有任何
      content 又没有 [DONE]，视为异常抛 ValueError。
    """
    chunks: list[str] = []
    received_done = False
    async with client.stream("POST", path, json={**payload, "stream": True}) as resp:
        if resp.status_code >= 400:
            body = (await resp.aread()).decode("utf-8", errors="replace")[:1000]
            raise httpx.HTTPStatusError(
                f"upstream_returned_{resp.status_code} body={body}",
                request=resp.request,
                response=resp,
            )
        async for raw_line in resp.aiter_lines():
            if not raw_line:
                continue
            # 兼容 OpenAI 官方格式：每条数据行以 "data: " 开头
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                received_done = True
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                # 个别中转网关可能塞 keep-alive 噪音，忽略
                continue
            try:
                delta = obj["choices"][0].get("delta") or {}
            except (KeyError, IndexError):
                continue
            piece = delta.get("content")
            if piece:
                chunks.append(piece)
    if not chunks and not received_done:
        raise ValueError("stream_returned_empty_response")
    return "".join(chunks)


def _parse_json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model_json_response_must_be_object")
    return parsed


def _schema_field_summary(schema: dict[str, Any]) -> str:
    properties = schema.get("properties") or {}
    if not properties:
        return "按用户要求的字段返回。"
    fields = []
    for name, field_schema in properties.items():
        field_type = field_schema.get("type")
        if not field_type and "$ref" in field_schema:
            field_type = "object"
        if not field_type and "anyOf" in field_schema:
            field_type = "|".join(
                item.get("type", "object") for item in field_schema["anyOf"]
            )
        if field_type == "array":
            item_type = (field_schema.get("items") or {}).get("type", "object")
            field_type = f"array[{item_type}]"
        fields.append(f"{name}:{field_type or 'string'}")
    return "顶层字段包括：" + ", ".join(fields) + "。"


class OpenAIChatProvider:
    """OpenAI Chat Completions API provider。

    依赖：仅 httpx，不依赖官方 SDK，以减小镜像体积。

    stream 参数：
    - False（默认）：走非流式 /chat/completions
    - True：走 SSE 流式。**许多 OpenAI 中转网关强制要求 stream=true**，
      非流式请求会被 400 `Stream must be set to true` 拒。生产环境对接
      中转 API 时建议开启。OpenAI 官方也兼容 stream，开了不会有副作用
      （除了响应延迟稍高几十毫秒）。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 300.0,
        stream: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.stream = stream
        self._use_response_format = "api.openai.com" in self.base_url

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def complete_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        async with self._client() as client:
            if self.stream:
                return await _stream_chat_completion(
                    client, "/chat/completions", payload=payload
                )
            response = await _post_json(
                client,
                "/chat/completions",
                payload=payload,
                timeout_seconds=self.timeout,
            )
            _raise_for_status(response)
            data = response.json()
        return data["choices"][0]["message"]["content"]

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any]:
        schema_instruction = (
            "请严格按以下字段约束返回 JSON 对象，不要附加自然语言：\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
            if self._use_response_format
            else (
                "请用对象格式回复，只输出可解析 JSON。"
                f"{_schema_field_summary(schema)}"
            )
        )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"{user_prompt}\n\n{schema_instruction}",
                },
            ],
            "temperature": temperature,
        }
        if self._use_response_format:
            payload["response_format"] = {"type": "json_object"}

        async with self._client() as client:
            if self.stream:
                # 流式分支：拼出完整文本后走原有 _parse_json_from_text；
                # response_format 在中转 API 上常不支持，stream 失败时摘掉它再试一次。
                try:
                    text = await _stream_chat_completion(
                        client, "/chat/completions", payload=payload
                    )
                except httpx.HTTPStatusError:
                    if "response_format" not in payload:
                        raise
                    fallback = dict(payload)
                    fallback.pop("response_format", None)
                    text = await _stream_chat_completion(
                        client, "/chat/completions", payload=fallback
                    )
                return _parse_json_from_text(text)
            response = await _post_json(
                client,
                "/chat/completions",
                payload=payload,
                timeout_seconds=self.timeout,
            )
            try:
                _raise_for_status(response)
            except httpx.HTTPStatusError:
                if "response_format" not in payload:
                    raise
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                response = await _post_json(
                    client,
                    "/chat/completions",
                    payload=fallback_payload,
                    timeout_seconds=self.timeout,
                )
                _raise_for_status(response)
            data = response.json()
        return _parse_json_from_text(data["choices"][0]["message"]["content"])


class AnthropicMessagesProvider:
    """Anthropic Messages API provider。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 300.0,
        max_tokens: int = 4096,
        anthropic_version: str = "2023-06-01",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.anthropic_version = anthropic_version

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
                "Content-Type": "application/json",
            },
        )

    async def complete_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        async with self._client() as client:
            response = await _post_json(
                client,
                "/messages",
                payload={
                    "model": model,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "temperature": temperature,
                    "max_tokens": self.max_tokens,
                },
                timeout_seconds=self.timeout,
            )
            _raise_for_status(response)
            data = response.json()
        # Anthropic 返回 content 数组，取第一个 text 块
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
        return ""

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any]:
        prompt = (
            f"{user_prompt}\n\n"
            f"请严格按以下字段约束返回 JSON 对象，不要附加任何自然语言：\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        text = await self.complete_text(
            model=model,
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=temperature,
        )
        return _parse_json_from_text(text)
