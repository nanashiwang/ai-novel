"""通用分页 / 排序参数。

所有 list_* 端点统一接收：?page=1&page_size=20&sort=-created_at
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Query


@dataclass
class Pagination:
    page: int = 1
    page_size: int = 20
    sort: str | None = None

    @property
    def offset(self) -> int:
        return (max(1, self.page) - 1) * max(1, self.page_size)

    @property
    def limit(self) -> int:
        return max(1, min(self.page_size, 200))


def paginate(
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    sort: Annotated[str | None, Query(max_length=64)] = None,
) -> Pagination:
    return Pagination(page=page, page_size=page_size, sort=sort)


PaginationDep = Annotated[Pagination, ...]  # 仅类型提示，实际通过 Depends(paginate) 注入
