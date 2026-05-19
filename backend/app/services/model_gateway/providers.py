"""可插拔的 Model Provider。

约定：
- complete_text：返回纯文本
- complete_json：要求模型按 schema 返回 JSON，调用方负责 schema 约束

OpenAI / Anthropic 都通过 HTTP client 调用，避免强依赖 SDK；
真实部署可通过 `model_gateway.set_provider(...)` 注入自实现 client。
"""
from __future__ import annotations

import json
from typing import Any

import httpx


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
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
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
        async with self._client() as client:
            response = await client.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                },
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
            response = await client.post("/chat/completions", json=payload)
            try:
                _raise_for_status(response)
            except httpx.HTTPStatusError:
                if "response_format" not in payload:
                    raise
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                response = await client.post("/chat/completions", json=fallback_payload)
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
        timeout: float = 60.0,
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
            response = await client.post(
                "/messages",
                json={
                    "model": model,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "temperature": temperature,
                    "max_tokens": self.max_tokens,
                },
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
