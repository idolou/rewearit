"""Async database engine, session management, and schema initialization."""
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app.core.config import settings

_engine_kwargs: dict[str, object] = {
    "echo": settings.DB_ECHO,
    "future": True,
}
if settings.ENVIRONMENT == "test":
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    _engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async SQLAlchemy/SQLModel session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Ensure database tables and incremental columns are created."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        if conn.dialect.name == "postgresql":
            await conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS color VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS material VARCHAR(100)"))
