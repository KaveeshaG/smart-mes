from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from loguru import logger

from .settings import settings


class Base(DeclarativeBase):
    pass


# Re-use the same Neon PostgreSQL instance — AI agent gets its own tables
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create agent-specific tables if they don't exist."""
    # Import models so metadata is populated before create_all
    from ..models.db import audit_model, safety_bounds_model  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("AI agent database tables initialised")


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
