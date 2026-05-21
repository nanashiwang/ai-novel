"""ContextBuilder 服务模块。

把 scene 计划/写作所需的多源上下文按固定优先级与 token 预算组装成一份
确定性的 prompt segment 列表。借鉴 SillyTavern 的 World Info / Lorebook
插入顺序思想（clean-room 实现，未复用其代码），针对小说生成场景做了
取舍：trusted 上下文（圣经、人物卡、世界规则）优先满预算，untrusted
（向量召回、用户编辑过的 memory）放在低优先级且额度受限。

Sprint 3 实现范围（KISS）：
- 7 段硬编码顺序，固定预算占比
- 向量召回**暂不接入**，预留位置；Sprint 4-5 引入 pgvector 时再填
- token 估算复用 model_gateway._estimate_tokens（CJK 1 char/token）

Sprint 14-C4：在 characters 之后插入 style_samples 段，按当前 scene 的
title/goal/conflict 做 embedding 召回 top-K 用户上传的风格样本。
memory_recall 预算从 0.15 缩到 0.09，新增段占 0.06，总和保持 1.0。

参考：docs/api_contract_v1.md §5；优化方向.md §3.6。
"""
from .service import (
    BuiltContext,
    ContextBuilder,
    ContextSegment,
    context_builder,
)

__all__ = [
    "BuiltContext",
    "ContextBuilder",
    "ContextSegment",
    "context_builder",
]
