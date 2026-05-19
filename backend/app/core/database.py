from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

# SQLite (测试 / 本地) 不支持 pool_size 等参数；这里按 dialect 选择
_engine_kwargs: dict = {"echo": settings.environment == "local"}
if not settings.database_url.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=settings.db_pool_pre_ping,
        pool_recycle=1800,
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(AsyncSession.sync_session_class, "after_commit")
def _run_after_commit_tasks(session) -> None:
    tasks = session.info.pop("after_commit_tasks", [])
    if not tasks:
        return
    from app.workflows.starter import workflow_starter  # noqa: PLC0415

    for task_type, job_id in tasks:
        if task_type == "generate_bible":
            workflow_starter.run_local_generate_bible(job_id)
        elif task_type == "full_novel":
            workflow_starter.run_local_generate_full_novel(job_id)
        elif task_type == "scene_write":
            workflow_starter.run_local_write_scene(job_id)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
