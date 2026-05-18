"""统一的 API 依赖。"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import CurrentUser, get_current_user
from app.core.tenancy import TenantContext, resolve_tenant


async def db_session_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[AsyncSession]:
    """直接复用 get_db_session 以便统一注入。"""
    yield session


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
TenantDep = Annotated[TenantContext, Depends(resolve_tenant)]
DbDep = Annotated[AsyncSession, Depends(get_db_session)]
