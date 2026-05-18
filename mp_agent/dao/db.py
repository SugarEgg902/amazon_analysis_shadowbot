# mp_agent/dao/db.py
from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.config import DB_URL

engine = create_async_engine(DB_URL, pool_pre_ping=True, echo=False)
_SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_async_session() -> AsyncSession:
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
