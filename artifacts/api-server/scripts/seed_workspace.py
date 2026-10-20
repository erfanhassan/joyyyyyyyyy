"""Initialize the storefront expected by the imported UI, without replacing data."""
import asyncio
from uuid import UUID
from sqlalchemy.dialects.postgresql import insert
from app.db.models import Tenant
from app.db.session import async_engine


async def main():
    async with async_engine.begin() as connection:
        await connection.execute(
            insert(Tenant).values(
                id=UUID("a1e6f58d-b575-420e-b4d6-1fef0064e746"),
                name="My Storefront",
            ).on_conflict_do_nothing(index_elements=["id"])
        )
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
