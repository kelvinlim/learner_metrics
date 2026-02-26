from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from backend.config import settings
from backend.models import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

from backend.context import get_current_tenant


async def get_db():
    """Get database session with RLS tenant context set."""
    async with AsyncSessionLocal() as session:
        t_id = get_current_tenant()
        if t_id is not None:
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(t_id)},
            )
        try:
            yield session
        finally:
            await session.close()


async def get_db_no_rls():
    """Get database session WITHOUT RLS context.

    IMPORTANT: Only use this for authentication operations that need
    to query global tables (identities, tenant_memberships).
    Do NOT use for any tenant-scoped data queries.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
