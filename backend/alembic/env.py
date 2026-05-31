"""Alembic 异步迁移环境配置。"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# 加载所有 model 以便 Alembic 自动识别表结构
import app.models  # noqa: F401  # 触发所有 model 注册到 Base.metadata
from alembic import context
from app.core.config import get_settings
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _ensure_postgres_version_table(connection: Connection) -> None:
    """部分 revision id 超过 Alembic 默认 32 位，Postgres 需要放宽长度。"""
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS alembic_version (
          version_num VARCHAR(128) NOT NULL
        )
        """
    )
    connection.exec_driver_sql(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = 'alembic_version'::regclass
              AND contype = 'p'
          ) THEN
            ALTER TABLE alembic_version
            ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);
          END IF;
        END $$;
        """
    )
    connection.exec_driver_sql(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"
    )


def run_migrations_offline() -> None:
    """离线模式生成 SQL 脚本。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _ensure_postgres_version_table(connection)
    if connection.dialect.name == "postgresql" and connection.in_transaction():
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
