"""仓储层基础类。

提供针对单表的常用 CRUD 与租户隔离查询。所有具体 repository 应继承此基��类，
通过覆盖 `model` 与 `id_prefix` 完成 60% 以上场景；剩余复杂查询单独实现。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.common import new_id

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]
    id_prefix: str = "row"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        organization_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        order_by: Any = None,
        **filters: Any,
    ) -> Sequence[ModelT]:
        stmt = select(self.model)
        if organization_id is not None and hasattr(self.model, "organization_id"):
            stmt = stmt.where(self.model.organization_id == organization_id)  # type: ignore[attr-defined]
        for key, value in filters.items():
            if value is None:
                continue
            stmt = stmt.where(getattr(self.model, key) == value)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        elif hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())  # type: ignore[attr-defined]
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, row_id: str, *, organization_id: str | None = None) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == row_id)  # type: ignore[attr-defined]
        if organization_id is not None and hasattr(self.model, "organization_id"):
            stmt = stmt.where(self.model.organization_id == organization_id)  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by(self, **filters: Any) -> ModelT | None:
        stmt = select(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **values: Any) -> ModelT:
        values.setdefault("id", new_id(self.id_prefix))
        entity = self.model(**values)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(
        self,
        row_id: str,
        values: dict[str, Any],
        *,
        organization_id: str | None = None,
    ) -> ModelT | None:
        entity = await self.get(row_id, organization_id=organization_id)
        if not entity:
            return None
        for key, value in values.items():
            setattr(entity, key, value)
        await self.session.flush()
        return entity

    async def delete(self, row_id: str, *, organization_id: str | None = None) -> bool:
        entity = await self.get(row_id, organization_id=organization_id)
        if not entity:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True

    async def count(self, *, organization_id: str | None = None, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        if organization_id is not None and hasattr(self.model, "organization_id"):
            stmt = stmt.where(self.model.organization_id == organization_id)  # type: ignore[attr-defined]
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
