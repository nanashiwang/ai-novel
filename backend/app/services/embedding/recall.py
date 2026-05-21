"""语义召回查询助手（Sprint 13-B1）。

封装基于 pgvector 的余弦相似度召回，对外暴露最简调用面。注意：
- 仅在 PostgreSQL 上有效；其它方言会抛 NotImplementedError
- 召回结果按 `<=>` 余弦距离升序（值越小越相似）
- 不在内部 embed query；调用方自行用 embedding_service.embed 拿到向量后传入
  这样上游可以做缓存、debug 打印等
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry


async def recall_memories_by_vector(
    session: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    query_vector: list[float],
    k: int = 5,
    memory_types: Sequence[str] | None = None,
) -> list[MemoryEntry]:
    """按向量相似度召回 memory_entries。

    memory_types 为 None 时不过滤；传入时按 IN 过滤（如只要 character_state /
    world_state / plot_thread_state）。

    上游若运行在 SQLite 上（单测），直接调用会因 pgvector 操作符不存在而失败。
    上游应在调用前判断 dialect.name == "postgresql"，或对召回失败做软处理。
    """
    dialect = session.bind.dialect.name if session.bind else ""
    if dialect != "postgresql":
        raise NotImplementedError(
            "recall_memories_by_vector requires postgresql + pgvector"
        )

    # SQLAlchemy bindparam 无法直接处理 list[float] → vector 字面量；
    # 显式 cast 成 vector，并把 list 用字符串字面量传入。
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
    sql = """
        SELECT *
        FROM memory_entries
        WHERE organization_id = :org_id
          AND project_id = :project_id
          AND embedding IS NOT NULL
          {type_clause}
        ORDER BY embedding <=> (:vec)::vector
        LIMIT :k
    """
    type_clause = ""
    params = {
        "org_id": organization_id,
        "project_id": project_id,
        "vec": vec_literal,
        "k": k,
    }
    if memory_types:
        type_clause = "AND memory_type = ANY(:mtypes)"
        params["mtypes"] = list(memory_types)
    stmt = text(sql.format(type_clause=type_clause))
    if memory_types:
        stmt = stmt.bindparams(bindparam("mtypes", expanding=False))
    rows = (await session.execute(stmt, params)).mappings().all()
    # 把 mapping 行手动映射回 ORM 实体；不通过 ORM 加载避免再次查询
    entries: list[MemoryEntry] = []
    for row in rows:
        entry = MemoryEntry(**{k: row[k] for k in row.keys() if hasattr(MemoryEntry, k)})
        entries.append(entry)
    return entries
