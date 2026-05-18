import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from mp_agent.application.agent_service import (
    EventQueue,
    new_run,
    run_session_message,
)
from mp_agent.application.session_store import SessionStore


def _collect(queue):
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


@pytest.mark.asyncio
async def test_run_session_message_creates_crawl_task():
    """crawl_task is created when a workflow is dispatched."""
    store = SessionStore()
    session = store.create_session()
    runs = {}
    run = new_run(session.session_id, "分析 doogee", session_store=store, runs=runs)

    mock_result = {
        "platform": "amazon", "brand": "doogee", "count": 5,
        "rows": [], "preview_columns": [], "preview_rows": [],
        "filename": "test.csv", "download_url": "/api/download/test.csv",
        "summary": "完成",
    }

    class FakeRegistry:
        def get_tool_schemas(self):
            return []

        async def call_tool(self, name, arguments, emit):
            return mock_result

    def fake_decide(messages, slots, tool_schemas):
        return {
            "type": "tool_call",
            "tool_name": "run_amazon_competitor_analysis",
            "arguments": {"brand": "doogee", "count": 5},
            "slot_updates": {},
            "assistant_message": None,
        }

    with patch("mp_agent.application.agent_service.create_crawl_task", new_callable=AsyncMock, return_value=42) as mock_create, \
         patch("mp_agent.application.agent_service.update_crawl_task", new_callable=AsyncMock) as mock_update:

        await run_session_message(
            session.session_id,
            run.run_id,
            run.queue,
            session_store=store,
            workflow_registry=FakeRegistry(),
            decide_next_step_fn=fake_decide,
            summarize_result_fn=lambda tool_name, tool_result: "完成",
            runs=runs,
        )

        mock_create.assert_called_once_with("amazon", "doogee", 5)
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] == 42   # task_id
        assert call_args[0][1] == "done"  # status


@pytest.mark.asyncio
async def test_run_session_message_updates_task_failed_on_error():
    """crawl_task is marked failed when workflow raises."""
    store = SessionStore()
    session = store.create_session()
    runs = {}
    run = new_run(session.session_id, "分析 doogee", session_store=store, runs=runs)

    class FailingRegistry:
        def get_tool_schemas(self):
            return []

        async def call_tool(self, name, arguments, emit):
            raise RuntimeError("scrape failed")

    def fake_decide(messages, slots, tool_schemas):
        return {
            "type": "tool_call",
            "tool_name": "run_amazon_competitor_analysis",
            "arguments": {"brand": "doogee", "count": 5},
            "slot_updates": {},
            "assistant_message": None,
        }

    with patch("mp_agent.application.agent_service.create_crawl_task", new_callable=AsyncMock, return_value=99), \
         patch("mp_agent.application.agent_service.update_crawl_task", new_callable=AsyncMock) as mock_update:

        await run_session_message(
            session.session_id,
            run.run_id,
            run.queue,
            session_store=store,
            workflow_registry=FailingRegistry(),
            decide_next_step_fn=fake_decide,
            summarize_result_fn=lambda tool_name, tool_result: "",
            runs=runs,
        )

        mock_update.assert_called_once()
        assert mock_update.call_args[0][0] == 99    # task_id
        assert mock_update.call_args[0][1] == "failed"  # status
