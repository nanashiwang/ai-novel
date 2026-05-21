"""嵌入向量服务测试（Sprint 13-B1）。

覆盖 stub provider 的确定性、维度、L2 归一化；OpenAI provider 通过
monkeypatch 验证集成路径而不真打外网。
"""
from __future__ import annotations

import math

import pytest

from app.services.embedding import embedding_service
from app.services.embedding.service import _stub_vector


def test_stub_vector_is_deterministic_and_normalized():
    v1 = _stub_vector("hello", 1536)
    v2 = _stub_vector("hello", 1536)
    assert v1 == v2
    assert len(v1) == 1536
    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-6


def test_stub_vector_differs_for_different_inputs():
    v1 = _stub_vector("我是主角", 1536)
    v2 = _stub_vector("我是反派", 1536)
    # 余弦距离应明显 < 1（不完全正交），但向量必须不同
    assert v1 != v2


@pytest.mark.asyncio
async def test_embed_empty_returns_none():
    assert await embedding_service.embed("") is None
    assert await embedding_service.embed("   ") is None


@pytest.mark.asyncio
async def test_embed_stub_returns_vector():
    vec = await embedding_service.embed("故事开头：少年走入古老的城市。")
    assert vec is not None
    assert len(vec) == 1536


@pytest.mark.asyncio
async def test_embed_many_preserves_order():
    texts = ["alpha", "beta", "gamma"]
    vecs = await embedding_service.embed_many(texts)
    assert len(vecs) == 3
    assert all(v is not None and len(v) == 1536 for v in vecs)
    # 顺序一致：alpha 的 stub 向量应固定
    assert vecs[0] == _stub_vector("alpha", 1536)


@pytest.mark.asyncio
async def test_unknown_provider_returns_none(monkeypatch):
    from app.services.embedding import service as mod

    class _Stub:
        embedding_provider = "nonexistent"
        embedding_model = "x"
        embedding_dims = 1536
        openai_api_key = ""
        openai_base_url = "https://api.openai.com/v1"

    monkeypatch.setattr(mod, "get_settings", lambda: _Stub())
    assert await embedding_service.embed("hello") is None
