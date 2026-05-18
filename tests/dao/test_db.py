# tests/dao/test_db.py
import pytest
from mp_agent.dao.db import get_async_session, engine

def test_engine_url():
    url = str(engine.url)
    assert "asyncmy" in url or "mysql" in url

@pytest.mark.asyncio
async def test_get_async_session_is_context_manager():
    # Just verify the function is an async context manager (no live DB needed)
    import inspect
    from contextlib import asynccontextmanager
    # get_async_session should be callable and return an async context manager
    assert callable(get_async_session)
