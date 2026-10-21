from typing import AsyncGenerator
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from starlette.requests import HTTPConnection, Request
from fastapi import HTTPException
from sqlalchemy import select, event
from sqlalchemy.orm import with_loader_criteria
from app.db.models import WorkspaceIdentity, Base, Tenant

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


@event.listens_for(AsyncSession.sync_session_class, "after_begin")
def restore_tenant_scope(session, transaction, connection):
    """Every new transaction, including after route commits, restores local RLS."""
    tenant = session.info.get("tenant_id")
    if tenant:
        connection.execute(text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                           {"tenant_id": str(tenant)})


@event.listens_for(AsyncSession.sync_session_class, "do_orm_execute")
def enforce_orm_workspace(execute_state):
    value = execute_state.session.info.get("tenant_id")
    if not value or not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        return
    tenant = UUID(str(value))
    # Authorization does not depend on the managed DB owner's RLS bypass flag.
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if model is WorkspaceIdentity:
            continue  # Auth registry is looked up only by the verified Clerk subject.
        column = Tenant.id if model is Tenant else getattr(model, "tenant_id", None)
        if column is not None:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(model, column == tenant, include_aliases=True))


@event.listens_for(AsyncSession.sync_session_class, "before_flush")
def reject_cross_workspace_writes(session, flush_context, instances):
    value = session.info.get("tenant_id")
    if not value:
        return
    for row in session.new.union(session.dirty):
        tenant = getattr(row, "tenant_id", None)
        if tenant is not None and str(tenant) != str(value):
            raise HTTPException(403, "Cross-workspace writes are not permitted.")


async def get_db(connection: HTTPConnection, tenant_id: UUID | None = None) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a tenant-scoped async database session.
    If tenant_id is provided, sets PostgreSQL session variable 'app.current_tenant_id'
    to automatically enforce Row-Level Security (RLS).
    """
    async with AsyncSessionLocal() as session:
        state = connection.scope.get("state", {})
        candidate = tenant_id or connection.path_params.get("tenant_id") or connection.query_params.get("tenant_id")
        if not candidate and isinstance(connection, Request):
            content_type = connection.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    candidate = (await connection.json()).get("tenant_id")
                except (ValueError, AttributeError):
                    pass
            elif "multipart/form-data" in content_type:
                candidate = (await connection.form()).get("tenant_id")
        try:
            selected = UUID(str(candidate)) if candidate else None
        except ValueError:
            raise HTTPException(400, "Invalid workspace identifier.") from None
        if state.get("clerk_user_id"):
            identity = (await session.execute(select(WorkspaceIdentity).where(
                WorkspaceIdentity.clerk_user_id == state["clerk_user_id"]))).scalar_one_or_none()
            if selected and not state.get("is_joy_owner"):
                if not identity or identity.tenant_id != selected:
                    raise HTTPException(403, "You are not a member of this workspace.")
                if connection.scope.get("method", "GET") not in ("GET", "HEAD") and identity.role not in ("owner", "admin", "operator"):
                    raise HTTPException(403, "This workspace role cannot make changes.")
                if (identity.role == "operator" and connection.scope.get("method", "GET") not in ("GET", "HEAD")
                        and "/workbench" not in connection.url.path):
                    raise HTTPException(403, "Only a workspace owner or admin can change settings.")
            if not selected and identity:
                selected = identity.tenant_id
        if selected:
            session.info["tenant_id"] = str(selected)
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(selected)},
            )
        try:
            yield session
        finally:
            await session.close()
