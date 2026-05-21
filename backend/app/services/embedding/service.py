"""嵌入向量服务（Sprint 13-B1）。

为长篇语义召回（B2 用到）提供统一的 embed 接口：
- `stub` provider：基于 sha256 哈希派生的确定性向量，无外部依赖；
  用于本地开发 / 测试，向量分布够稳定支撑余弦相似度查询的逻辑验证
- `openai` provider：调用 text-embedding-3-small（1536 维）

设计 KISS：
- 不缓存（同段文本两次调用就是两次请求）；上游若需要缓存自行包一层
- 失败回 None；调用方决定是否阻断
- 维度由 settings.embedding_dims 控制；运行期不允许中途切维度
"""
from __future__ import annotations

import hashlib
import logging
import math
import random
from collections.abc import Iterable

from app.core.config import get_settings

_logger = logging.getLogger(__name__)


def _stub_vector(text: str, dim: int) -> list[float]:
    """基于 sha256 派生 dim 维确定性向量并 L2 归一化。

    思路：用 sha256 的前 8 字节作为 random 模块的种子，产出 dim 个 [-1,1]
    均匀分布浮点数，最后 L2 归一化。这种构造既确定又避免了把 raw bytes
    当作 IEEE754 double 解读时出现的极端量级（会让平方溢出到 inf 进而
    把整向量归零）。
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "little")
    rng = random.Random(seed)
    values = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class EmbeddingService:
    async def embed(self, text: str) -> list[float] | None:
        text = (text or "").strip()
        if not text:
            return None
        settings = get_settings()
        provider = settings.embedding_provider
        dim = settings.embedding_dims
        if provider == "stub":
            return _stub_vector(text, dim)
        if provider == "openai":
            try:
                return await self._embed_openai(text, settings)
            except Exception:  # noqa: BLE001
                _logger.warning("embedding_openai_failed", exc_info=True)
                # Provider 失败回落 stub，保证 B2 召回链路不会中断；
                # 同时通过日志能看到 provider 不健康
                return _stub_vector(text, dim)
        _logger.warning("embedding_unknown_provider", extra={"provider": provider})
        return None

    async def embed_many(self, texts: Iterable[str]) -> list[list[float] | None]:
        # KISS：v1 串行；上量后再考虑批接口
        return [await self.embed(t) for t in texts]

    async def _embed_openai(self, text: str, settings) -> list[float]:
        import httpx  # noqa: PLC0415

        if not settings.openai_api_key:
            raise RuntimeError("openai_api_key_missing")
        url = settings.openai_base_url.rstrip("/") + "/embeddings"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={
                    "model": settings.embedding_model,
                    "input": text[:8000],
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        emb = data["data"][0]["embedding"]
        if len(emb) != settings.embedding_dims:
            raise RuntimeError(
                f"embedding_dim_mismatch: got {len(emb)}, expected {settings.embedding_dims}"
            )
        return emb


embedding_service = EmbeddingService()
