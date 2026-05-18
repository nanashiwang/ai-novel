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
            response.raise_for_status()
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
        async with self._client() as client:
            response = await client.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": (
                                f"{user_prompt}\n\n"
                                f"请严格按以下 JSON Schema 返回，不要附加自然语言：\n"
                                f"{json.dumps(schema, ensure_ascii=False)}"
                            ),
                        },
                    ],
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()
        return json.loads(data["choices"][0]["message"]["content"])


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
            response.raise_for_status()
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
            f"请严格按以下 JSON Schema 返回 JSON 对象，不要附加任何自然语言：\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        text = await self.complete_text(
            model=model,
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=temperature,
        )
        # 容错：尝试找到第一个 { 与最后一个 }
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
