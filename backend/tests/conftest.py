"""pytest 全局 fixtures。

使用 in-memory SQLite + aiosqlite 提供独立的 async db；
覆盖 FastAPI 应用的 dependency_overrides，让 get_db_session 返回测试 session。
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("JWT_SECRET", "test-secret-min-32-chars-aaaaaaaa")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db_session
from app.main import app


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_engine) -> AsyncIterator[AsyncClient]:
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db_session():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolate_model_gateway():
    """每个测试前后重置 ModelGateway 状态。

    ModelGateway 是模块级单例，admin settings 测试会调用 configure() 注入
    真实 OpenAI provider；同进程后续测试（如 generate_bible_flow）会沿用
    这个 provider，对空的内存 sqlite 报 401。
    通过失效 settings 缓存让每个测试的首次 generate 强制查库回到 mock。
    """
    from app.services.model_gateway.service import _MockProvider, model_gateway

    model_gateway._provider = _MockProvider()
    model_gateway.invalidate_settings_cache()
    yield
    model_gateway._provider = _MockProvider()
    model_gateway.invalidate_settings_cache()
