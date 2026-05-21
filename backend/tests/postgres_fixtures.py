"""Postgres 集成测试 fixture。

仅当环境中可用 Docker 时启用 testcontainers Postgres，用以验证：
- SELECT ... FOR UPDATE 真锁
- ON DELETE CASCADE
- JSONB 字段

启用方式：`pytest -m postgres`；缺少 Docker 时整组测试 skip。
"""
from __future__ import annotations

import importlib.util
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base


def _testcontainers_available() -> bool:
    if importlib.util.find_spec("testcontainers") is None:
        return False
    if not os.environ.get("DOCKER_HOST") and not os.path.exists("/var/run/docker.sock"):
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _testcontainers_available(),
    reason="testcontainers 或 Docker 不可用，跳过 Postgres 集成测试",
)


@pytest_asyncio.fixture(scope="session")
async def pg_url() -> AsyncIterator[str]:
    from testcontainers.postgres import PostgresContainer

    # 使用 pgvector 官方镜像，保证 memory_entries.embedding 列（vector 类型）
    # 可成功建表；postgres:16-alpine 没有 pgvector 扩展。
    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()
    try:
        url = container.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield url
    finally:
        container.stop()


@pytest_asyncio.fixture(scope="function")
async def pg_engine(pg_url: str):
    from sqlalchemy import text

    engine = create_async_engine(pg_url, future=True)
    async with engine.begin() as conn:
        # pgvector 扩展必须先于 create_all 创建，否则 vector(1536) 列建表失败
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def pg_session(pg_engine) -> AsyncIterator[AsyncSession]:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session
