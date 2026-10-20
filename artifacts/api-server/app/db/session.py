from typing import AsyncGenerator
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

def normalize_db_url(url: str, is_async: bool = False) -> str:
    if not url:
        return url
    normalized = url
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)
    
    if is_async:
        if "postgresql+asyncpg://" not in normalized:
            if normalized.startswith("postgresql://"):
                normalized = normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif normalized.startswith("postgresql+psycopg2://"):
                normalized = normalized.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if "sslmode=" in normalized:
            normalized = normalized.replace("sslmode=", "ssl=")
    else:
        if "postgresql+psycopg2://" not in normalized:
            if "postgresql+asyncpg://" in normalized:
                normalized = normalized.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
            elif normalized.startswith("postgresql://"):
                normalized = normalized.replace("postgresql://", "postgresql+psycopg2://", 1)
    return normalized

ASYNC_DB_URL = normalize_db_url(settings.DATABASE_URL, is_async=True)
SYNC_DB_URL = normalize_db_url(settings.DATABASE_URL, is_async=False)

# Async Engine and SessionMaker (used by FastAPI routes)
async_engine = create_async_engine(
    ASYNC_DB_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Synchronous Engine and SessionMaker (used by migrations/scripts)
sync_engine = create_engine(
    SYNC_DB_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)


async def get_db(tenant_id: UUID | None = None) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a tenant-scoped async database session.
    If tenant_id is provided, sets PostgreSQL session variable 'app.current_tenant_id'
    to automatically enforce Row-Level Security (RLS).
    """
    async with AsyncSessionLocal() as session:
        if tenant_id:
            # Set local tenant_id for RLS enforcement
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"),
                {"tenant_id": str(tenant_id)},
            )
        try:
            yield session
        finally:
            await session.close()
