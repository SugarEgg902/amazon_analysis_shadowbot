# Multi-Platform Competitor Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current regex-based single-turn Amazon flow with a multi-turn in-memory chat agent that asks follow-up questions, calls a high-level Amazon workflow tool, and streams mixed assistant plus artifact events.

**Architecture:** Add a focused in-memory session store, a primary agent module for DashScope `glm-4.6`, and a workflow registry that exposes only high-level competitor-analysis tools to the agent. Keep the existing Amazon scraping, review summary, analysis, and CSV helpers behind a single Amazon workflow wrapper, then refactor the FastAPI API and static frontend around `session_id` and `run_id`.

**Tech Stack:** Python 3, FastAPI, asyncio, OpenAI-compatible Chat Completions API, pytest, static HTML/CSS/JavaScript

---

## File Structure

**Create:**
- `session_store.py`
- `workflow_registry.py`
- `competitor_workflows.py`
- `primary_agent.py`
- `test_session_store.py`
- `test_workflow_registry.py`
- `test_primary_agent.py`
- `docs/superpowers/plans/2026-05-10-multiplatform-competitor-agent.md`

**Modify:**
- `agent_service.py`
- `app.py`
- `test_agent_service.py`
- `test_app.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `test_frontend_static.py`

**Responsibilities:**
- `session_store.py`: in-memory session, slot, history, and active-run management
- `workflow_registry.py`: registry of high-level workflow tools and their schemas
- `competitor_workflows.py`: Amazon competitor-analysis workflow wrapper around existing scraping/review/analysis/export helpers
- `primary_agent.py`: DashScope-backed primary agent client, tool-decision logic, and final-summary generation
- `agent_service.py`: session/run orchestration, SSE queue emission, and integration of store, agent, and workflow registry
- `app.py`: session-based HTTP API, SSE stream endpoint, and artifact download route
- `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`: session-based chat UI and mixed event rendering
- `test_session_store.py`, `test_workflow_registry.py`, `test_primary_agent.py`, `test_agent_service.py`, `test_app.py`, `test_frontend_static.py`: regression coverage for each layer

### Task 1: Add the In-Memory Session Store

**Files:**
- Create: `session_store.py`
- Create: `test_session_store.py`

- [ ] **Step 1: Write the failing session-store tests**

```python
from session_store import ConcurrentRunError, SessionStore


def test_create_session_starts_with_empty_history_and_slots():
    store = SessionStore()

    session = store.create_session()

    assert session.session_id
    assert session.messages == []
    assert session.slots.platform is None
    assert session.slots.brand is None
    assert session.slots.count is None
    assert session.active_run_id is None


def test_update_slots_and_append_message_preserve_existing_session_state():
    store = SessionStore()
    session = store.create_session()

    store.append_message(session.session_id, "user", "帮我看一下 Blackview 的竞品")
    store.update_slots(session.session_id, brand="Blackview")
    store.update_slots(session.session_id, count=5)

    saved = store.get_session(session.session_id)
    assert [(message.role, message.content) for message in saved.messages] == [
        ("user", "帮我看一下 Blackview 的竞品")
    ]
    assert saved.slots.platform is None
    assert saved.slots.brand == "Blackview"
    assert saved.slots.count == 5


def test_start_run_rejects_second_active_run_for_same_session():
    store = SessionStore()
    session = store.create_session()

    run_id = store.start_run(session.session_id)

    assert run_id

    try:
        store.start_run(session.session_id)
    except ConcurrentRunError as exc:
        assert "already active" in str(exc)
    else:
        raise AssertionError("ConcurrentRunError was not raised")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest test_session_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'session_store'`

- [ ] **Step 3: Write the minimal session-store implementation**

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class SessionSlots:
    platform: str | None = None
    brand: str | None = None
    count: int | None = None


@dataclass
class ChatSession:
    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    slots: SessionSlots = field(default_factory=SessionSlots)
    active_run_id: str | None = None


class ConcurrentRunError(RuntimeError):
    pass


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}

    def create_session(self) -> ChatSession:
        session = ChatSession(session_id=uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> ChatSession:
        return self._sessions[session_id]

    def append_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        session = self.get_session(session_id)
        message = ChatMessage(role=role, content=content)
        session.messages.append(message)
        return message

    def update_slots(
        self,
        session_id: str,
        *,
        platform: str | None = None,
        brand: str | None = None,
        count: int | None = None,
    ) -> SessionSlots:
        session = self.get_session(session_id)
        if platform is not None:
            session.slots.platform = platform
        if brand is not None:
            session.slots.brand = brand
        if count is not None:
            session.slots.count = count
        return session.slots

    def start_run(self, session_id: str) -> str:
        session = self.get_session(session_id)
        if session.active_run_id is not None:
            raise ConcurrentRunError(f"session {session_id} already active: {session.active_run_id}")

        run_id = uuid.uuid4().hex
        session.active_run_id = run_id
        return run_id

    def finish_run(self, session_id: str, run_id: str) -> None:
        session = self.get_session(session_id)
        if session.active_run_id == run_id:
            session.active_run_id = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest test_session_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add session_store.py test_session_store.py
git commit -m "feat: add in-memory session store"
```

### Task 2: Add the Workflow Registry and Amazon Workflow Wrapper

**Files:**
- Create: `workflow_registry.py`
- Create: `competitor_workflows.py`
- Create: `test_workflow_registry.py`

- [ ] **Step 1: Write the failing workflow tests**

```python
import asyncio

from competitor_workflows import run_amazon_competitor_analysis
from workflow_registry import build_default_registry


def _sample_product():
    return {
        "asin": "B0TEST1234",
        "url": "https://www.amazon.com/dp/B0TEST1234",
        "title": "Blackview Example",
        "price": "$199.99",
        "rating": "4.4 out of 5 stars",
        "review_count": "321",
        "bullets": ["Rugged", "Long battery"],
    }


def _sample_row():
    return {
        "品牌": "Blackview",
        "ASIN": "B0TEST1234",
        "url": "https://www.amazon.com/dp/B0TEST1234",
        "商品标题": "Blackview Example",
        "价格": "$199.99",
        "评分": "4.4 out of 5 stars",
        "评论数": "321",
        "核心卖点": "三防机身",
        "优点评炼": "续航长",
        "缺点评炼": "偏厚重",
        "综合分析": "适合户外",
        "竞品定位": "中低价三防竞品",
    }


def test_default_registry_exposes_amazon_workflow_schema():
    registry = build_default_registry()

    schemas = registry.get_tool_schemas()

    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "run_amazon_competitor_analysis"


def test_run_amazon_competitor_analysis_emits_status_and_returns_artifact(tmp_path):
    events = []
    product = _sample_product()
    row = _sample_row()

    async def fake_emit(payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [product]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row_builder(**_kwargs):
        return row

    result = asyncio.run(
        run_amazon_competitor_analysis(
            brand="Blackview",
            count=1,
            emit=fake_emit,
            scrape_products=fake_scrape,
            summarize_reviews_fn=fake_reviews,
            build_row_fn=fake_row_builder,
            write_csv_fn=lambda rows, brand, count: tmp_path / "out.csv",
            download_url_builder=lambda path: f"/api/download/{path.name}",
        )
    )

    assert events[0] == {
        "type": "tool_status",
        "tool": "run_amazon_competitor_analysis",
        "message": "正在抓取 Amazon 商品...",
    }
    assert result["platform"] == "amazon"
    assert result["brand"] == "Blackview"
    assert result["count"] == 1
    assert result["preview_rows"] == [[row[column] for column in result["preview_columns"]]]
    assert result["filename"] == "out.csv"
    assert result["download_url"] == "/api/download/out.csv"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest test_workflow_registry.py -v`
Expected: FAIL with `ModuleNotFoundError` for `workflow_registry` or `competitor_workflows`

- [ ] **Step 3: Write the minimal registry and workflow implementation**

```python
# workflow_registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from competitor_workflows import AMAZON_WORKFLOW_SCHEMA, run_amazon_competitor_analysis


WorkflowHandler = Callable[..., Awaitable[dict]]


@dataclass
class WorkflowTool:
    name: str
    schema: dict
    handler: WorkflowHandler


class WorkflowRegistry:
    def __init__(self):
        self._tools: dict[str, WorkflowTool] = {}

    def register(self, tool: WorkflowTool) -> None:
        self._tools[tool.name] = tool

    def get_tool_schemas(self) -> list[dict]:
        return [tool.schema for tool in self._tools.values()]

    async def call_tool(self, name: str, arguments: dict, emit) -> dict:
        tool = self._tools[name]
        return await tool.handler(emit=emit, **arguments)


def build_default_registry() -> WorkflowRegistry:
    registry = WorkflowRegistry()
    registry.register(
        WorkflowTool(
            name="run_amazon_competitor_analysis",
            schema=AMAZON_WORKFLOW_SCHEMA,
            handler=run_amazon_competitor_analysis,
        )
    )
    return registry
```

```python
# competitor_workflows.py
from __future__ import annotations

from pathlib import Path

from amazon_tools import scrape_amazon_products, summarize_reviews
from analysis_tools import build_analysis_row
from artifacts import CSV_COLUMNS, write_analysis_csv


AMAZON_WORKFLOW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_amazon_competitor_analysis",
        "description": "在 Amazon 上抓取指定品牌商品、总结评论、生成竞品分析并导出 CSV。",
        "parameters": {
            "type": "object",
            "properties": {
                "brand": {"type": "string"},
                "count": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["brand", "count"],
        },
    },
}


def _default_download_url(path: Path) -> str:
    return f"/api/download/{path.name}"


async def run_amazon_competitor_analysis(
    brand: str,
    count: int,
    emit,
    *,
    scrape_products=scrape_amazon_products,
    summarize_reviews_fn=summarize_reviews,
    build_row_fn=build_analysis_row,
    write_csv_fn=write_analysis_csv,
    download_url_builder=_default_download_url,
) -> dict:
    await emit(
        {
            "type": "tool_status",
            "tool": "run_amazon_competitor_analysis",
            "message": "正在抓取 Amazon 商品...",
        }
    )
    products = await scrape_products(brand, max_valid=count)
    if not products:
        raise RuntimeError("没有抓取到有效商品")

    rows: list[dict] = []
    for product in products:
        asin = product.get("asin", "")
        await emit(
            {
                "type": "tool_status",
                "tool": "run_amazon_competitor_analysis",
                "message": f"正在分析 {asin} ...",
            }
        )
        try:
            review_summary = await summarize_reviews_fn(asin)
        except Exception:
            review_summary = {"pros": [], "cons": [], "overall": ""}

        row = build_row_fn(
            brand=brand,
            product=product,
            review_summary=review_summary,
        )
        rows.append(row)

    csv_path = write_csv_fn(rows, brand=brand, count=count)
    return {
        "platform": "amazon",
        "brand": brand,
        "count": count,
        "rows": rows,
        "preview_columns": CSV_COLUMNS,
        "preview_rows": [[row.get(column, "") for column in CSV_COLUMNS] for row in rows],
        "filename": csv_path.name,
        "download_url": download_url_builder(csv_path),
        "summary": f"已完成 {len(rows)} 个竞品分析",
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest test_workflow_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add workflow_registry.py competitor_workflows.py test_workflow_registry.py
git commit -m "feat: add workflow registry and amazon workflow"
```

### Task 3: Add the DashScope Primary Agent Module

**Files:**
- Create: `primary_agent.py`
- Create: `test_primary_agent.py`

- [ ] **Step 1: Write the failing primary-agent tests**

```python
from primary_agent import (
    DASHSCOPE_BASE_URL,
    DASHSCOPE_MODEL,
    build_primary_agent_client,
    decide_next_step,
    summarize_workflow_result,
)
from session_store import ChatMessage, SessionSlots


def test_build_primary_agent_client_requires_dashscope_api_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    try:
        build_primary_agent_client()
    except RuntimeError as exc:
        assert "DASHSCOPE_API_KEY" in str(exc)
    else:
        raise AssertionError("RuntimeError was not raised")


def test_primary_agent_constants_match_dashscope_configuration():
    assert DASHSCOPE_BASE_URL == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert DASHSCOPE_MODEL == "glm-4.6"


def test_decide_next_step_returns_follow_up_question_when_slots_missing():
    def fake_llm(messages, tools):
        assert tools[0]["function"]["name"] == "run_amazon_competitor_analysis"
        assert any(message["role"] == "user" for message in messages)
        return {
            "type": "assistant",
            "message": "你想分析哪个平台？目前我支持 Amazon。",
            "slot_updates": {"brand": "Blackview"},
        }

    decision = decide_next_step(
        messages=[ChatMessage(role="user", content="帮我看一下 Blackview 的竞品")],
        slots=SessionSlots(),
        tool_schemas=[
            {
                "type": "function",
                "function": {"name": "run_amazon_competitor_analysis"},
            }
        ],
        llm_call=fake_llm,
    )

    assert decision == {
        "type": "assistant",
        "message": "你想分析哪个平台？目前我支持 Amazon。",
        "slot_updates": {"brand": "Blackview"},
    }


def test_decide_next_step_returns_tool_call_when_slots_are_complete():
    def fake_llm(_messages, _tools):
        return {
            "type": "tool_call",
            "tool_name": "run_amazon_competitor_analysis",
            "arguments": {"brand": "Blackview", "count": 5},
            "assistant_message": "好的，我开始分析 Amazon 上的 Blackview 竞品。",
            "slot_updates": {
                "platform": "amazon",
                "brand": "Blackview",
                "count": 5,
            },
        }

    decision = decide_next_step(
        messages=[ChatMessage(role="user", content="看 Amazon 的 Blackview，5 个")],
        slots=SessionSlots(platform="amazon"),
        tool_schemas=[
            {
                "type": "function",
                "function": {"name": "run_amazon_competitor_analysis"},
            }
        ],
        llm_call=fake_llm,
    )

    assert decision["type"] == "tool_call"
    assert decision["tool_name"] == "run_amazon_competitor_analysis"
    assert decision["arguments"] == {"brand": "Blackview", "count": 5}
    assert decision["slot_updates"]["platform"] == "amazon"


def test_decide_next_step_rejects_unsupported_tool_call():
    def fake_llm(_messages, _tools):
        return {
            "type": "tool_call",
            "tool_name": "run_temu_competitor_analysis",
            "arguments": {"brand": "Blackview", "count": 5},
            "slot_updates": {
                "platform": "temu",
                "brand": "Blackview",
                "count": 5,
            },
        }

    decision = decide_next_step(
        messages=[ChatMessage(role="user", content="看 Temu 的 Blackview，5 个")],
        slots=SessionSlots(),
        tool_schemas=[
            {
                "type": "function",
                "function": {"name": "run_amazon_competitor_analysis"},
            }
        ],
        llm_call=fake_llm,
    )

    assert decision == {
        "type": "assistant",
        "message": "目前只支持 Amazon 竞品分析，请改用 Amazon。",
        "slot_updates": {
            "platform": "temu",
            "brand": "Blackview",
            "count": 5,
        },
    }


def test_summarize_workflow_result_returns_final_assistant_copy():
    def fake_llm(messages, tools):
        assert tools == []
        assert any(message["role"] == "user" for message in messages)
        return {
            "type": "assistant",
            "message": "已完成 5 个 Amazon 竞品分析，CSV 已生成并可下载。",
        }

    summary = summarize_workflow_result(
        tool_name="run_amazon_competitor_analysis",
        tool_result={
            "platform": "amazon",
            "brand": "Blackview",
            "count": 5,
            "summary": "已完成 5 个竞品分析",
            "filename": "amazon_blackview_5.csv",
            "download_url": "/api/download/amazon_blackview_5.csv",
        },
        llm_call=fake_llm,
    )

    assert summary == "已完成 5 个 Amazon 竞品分析，CSV 已生成并可下载。"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest test_primary_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'primary_agent'`

- [ ] **Step 3: Write the minimal primary-agent implementation**

```python
from __future__ import annotations

import json
import os

from openai import OpenAI


DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_MODEL = "glm-4.6"


def build_primary_agent_client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not set")
    return OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE_URL)


def _history_to_messages(messages, slots) -> list[dict]:
    slot_state = {
        "platform": slots.platform,
        "brand": slots.brand,
        "count": slots.count,
    }
    system_prompt = (
        "你是电商竞品分析主代理。"
        "你只能决定是继续追问，还是调用高层平台工作流工具。"
        "如果 platform、brand、count 任一缺失，就追问缺失项，不要猜测。"
        f"当前已知槽位: {json.dumps(slot_state, ensure_ascii=False)}"
    )
    history = [{"role": "system", "content": system_prompt}]
    history.extend({"role": message.role, "content": message.content} for message in messages)
    return history


def _default_llm_call(messages: list[dict], tools: list[dict]) -> dict:
    client = build_primary_agent_client()
    response = client.chat.completions.create(
        model=DASHSCOPE_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.2,
    )
    message = response.choices[0].message
    if message.tool_calls:
        tool_call = message.tool_calls[0]
        return {
            "type": "tool_call",
            "tool_name": tool_call.function.name,
            "arguments": json.loads(tool_call.function.arguments or "{}"),
            "assistant_message": message.content or "",
            "slot_updates": {},
        }
    return {
        "type": "assistant",
        "message": message.content or "请补充平台、品牌和数量。",
        "slot_updates": {},
    }


def decide_next_step(messages, slots, tool_schemas, llm_call=None) -> dict:
    llm_call = llm_call or _default_llm_call
    decision = llm_call(_history_to_messages(messages, slots), tool_schemas)
    if decision.get("type") == "tool_call":
        supported_names = {schema["function"]["name"] for schema in tool_schemas}
        if decision.get("tool_name") not in supported_names:
            return {
                "type": "assistant",
                "message": "目前只支持 Amazon 竞品分析，请改用 Amazon。",
                "slot_updates": decision.get("slot_updates", {}),
            }
    return decision


def summarize_workflow_result(tool_name: str, tool_result: dict, llm_call=None) -> str:
    llm_call = llm_call or _default_llm_call
    messages = [
        {
            "role": "system",
            "content": "你是电商竞品分析主代理。根据工作流结果，为用户输出一条简洁中文总结。",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tool_name": tool_name,
                    "tool_result": tool_result,
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = llm_call(messages, [])
    return result.get("message", "") or tool_result.get("summary", "任务已完成。")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest test_primary_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add primary_agent.py test_primary_agent.py
git commit -m "feat: add dashscope primary agent"
```

### Task 4: Refactor the Service Layer Around Sessions and Runs

**Files:**
- Modify: `agent_service.py`
- Modify: `test_agent_service.py`

- [ ] **Step 1: Replace the parser tests with session-orchestration tests**

```python
import asyncio

from agent_service import RUNS, build_artifact_event, new_run, new_session, run_session_message
from session_store import SessionStore


def _collect(queue):
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def test_new_session_returns_session_from_store():
    store = SessionStore()

    session = new_session(session_store=store)

    assert session.session_id
    assert store.get_session(session.session_id) == session


def test_new_run_appends_user_message_and_marks_session_active():
    store = SessionStore()
    session = store.create_session()
    runs = {}

    run = new_run(
        session.session_id,
        "帮我看一下 Blackview 的竞品",
        session_store=store,
        runs=runs,
    )

    saved = store.get_session(session.session_id)
    assert run.run_id == saved.active_run_id
    assert saved.messages[-1].content == "帮我看一下 Blackview 的竞品"


def test_run_session_message_emits_follow_up_assistant_and_done():
    store = SessionStore()
    session = store.create_session()
    run = new_run(session.session_id, "帮我看一下 Blackview 的竞品", session_store=store, runs={})

    def fake_decide(messages, slots, tool_schemas):
        del messages, slots, tool_schemas
        return {
            "type": "assistant",
            "message": "你想分析哪个平台？目前我支持 Amazon。",
            "slot_updates": {"brand": "Blackview"},
        }

    asyncio.run(
        run_session_message(
            session.session_id,
            run.run_id,
            run.queue,
            session_store=store,
            workflow_registry=None,
            decide_next_step_fn=fake_decide,
            summarize_result_fn=lambda tool_name, tool_result: "",
            runs={},
        )
    )

    events = _collect(run.queue)
    assert events == [
        {"type": "assistant", "message": "你想分析哪个平台？目前我支持 Amazon。"},
        {"type": "done"},
    ]
    saved = store.get_session(session.session_id)
    assert saved.slots.brand == "Blackview"
    assert saved.messages[-1].content == "你想分析哪个平台？目前我支持 Amazon。"


def test_run_session_message_emits_artifact_and_final_summary():
    store = SessionStore()
    session = store.create_session()
    run = new_run(session.session_id, "看 Amazon 的 Blackview，5 个", session_store=store, runs={})
    events = []

    async def fake_emit_from_workflow(payload):
        events.append(payload)

    class FakeRegistry:
        def get_tool_schemas(self):
            return [{"type": "function", "function": {"name": "run_amazon_competitor_analysis"}}]

        async def call_tool(self, name, arguments, emit):
            assert name == "run_amazon_competitor_analysis"
            assert arguments == {"brand": "Blackview", "count": 5}
            await emit(
                {
                    "type": "tool_status",
                    "tool": "run_amazon_competitor_analysis",
                    "message": "正在抓取 Amazon 商品...",
                }
            )
            return {
                "platform": "amazon",
                "brand": "Blackview",
                "count": 5,
                "rows": [],
                "preview_columns": ["品牌", "ASIN"],
                "preview_rows": [["Blackview", "B0TEST1234"]],
                "filename": "amazon_blackview_5.csv",
                "download_url": "/api/download/amazon_blackview_5.csv",
                "summary": "已完成 5 个竞品分析",
            }

    def fake_decide(messages, slots, tool_schemas):
        del messages, slots, tool_schemas
        return {
            "type": "tool_call",
            "tool_name": "run_amazon_competitor_analysis",
            "arguments": {"brand": "Blackview", "count": 5},
            "assistant_message": "好的，我开始分析 Amazon 上的 Blackview 竞品。",
            "slot_updates": {
                "platform": "amazon",
                "brand": "Blackview",
                "count": 5,
            },
        }

    def fake_summary(_tool_name, _tool_result):
        return "已完成 5 个 Amazon 竞品分析，CSV 已生成并可下载。"

    asyncio.run(
        run_session_message(
            session.session_id,
            run.run_id,
            run.queue,
            session_store=store,
            workflow_registry=FakeRegistry(),
            decide_next_step_fn=fake_decide,
            summarize_result_fn=fake_summary,
            runs={run.run_id: run},
        )
    )

    queued = _collect(run.queue)
    assert queued == [
        {"type": "assistant", "message": "好的，我开始分析 Amazon 上的 Blackview 竞品。"},
        {"type": "tool_status", "tool": "run_amazon_competitor_analysis", "message": "正在抓取 Amazon 商品..."},
        build_artifact_event(
            {
                "platform": "amazon",
                "brand": "Blackview",
                "count": 5,
                "rows": [],
                "preview_columns": ["品牌", "ASIN"],
                "preview_rows": [["Blackview", "B0TEST1234"]],
                "filename": "amazon_blackview_5.csv",
                "download_url": "/api/download/amazon_blackview_5.csv",
                "summary": "已完成 5 个竞品分析",
            }
        ),
        {"type": "assistant", "message": "已完成 5 个 Amazon 竞品分析，CSV 已生成并可下载。"},
        {"type": "done"},
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest test_agent_service.py -v`
Expected: FAIL because `agent_service.py` does not yet expose `new_session`, `new_run`, `run_session_message`, or `build_artifact_event`

- [ ] **Step 3: Refactor `agent_service.py` to use sessions, runs, and the primary agent**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from primary_agent import decide_next_step, summarize_workflow_result
from session_store import SessionStore
from workflow_registry import build_default_registry


SESSION_STORE = SessionStore()
WORKFLOW_REGISTRY = build_default_registry()
RUNS: dict[str, "AgentRun"] = {}


@dataclass
class AgentRun:
    run_id: str
    session_id: str
    queue: asyncio.Queue


def new_session(*, session_store: SessionStore = SESSION_STORE):
    return session_store.create_session()


def get_session_payload(session_id: str, *, session_store: SessionStore = SESSION_STORE) -> dict:
    session = session_store.get_session(session_id)
    return {
        "session_id": session.session_id,
        "messages": [{"role": message.role, "content": message.content} for message in session.messages],
        "slots": {
            "platform": session.slots.platform,
            "brand": session.slots.brand,
            "count": session.slots.count,
        },
        "active_run_id": session.active_run_id,
    }


def new_run(
    session_id: str,
    message: str,
    *,
    session_store: SessionStore = SESSION_STORE,
    runs: dict[str, AgentRun] = RUNS,
) -> AgentRun:
    session_store.append_message(session_id, "user", message)
    run_id = session_store.start_run(session_id)
    run = AgentRun(run_id=run_id, session_id=session_id, queue=asyncio.Queue())
    runs[run.run_id] = run
    return run


async def emit_event(queue: asyncio.Queue, payload: dict) -> None:
    await queue.put(payload)


def build_artifact_event(result: dict) -> dict:
    return {
        "type": "artifact",
        "artifact_type": "csv_preview",
        "summary": result["summary"],
        "preview_columns": result["preview_columns"],
        "preview_rows": result["preview_rows"],
        "filename": result["filename"],
        "download_url": result["download_url"],
    }


async def run_session_message(
    session_id: str,
    run_id: str,
    queue: asyncio.Queue,
    *,
    session_store: SessionStore = SESSION_STORE,
    workflow_registry=WORKFLOW_REGISTRY,
    decide_next_step_fn=decide_next_step,
    summarize_result_fn=summarize_workflow_result,
    runs: dict[str, AgentRun] = RUNS,
) -> None:
    try:
        session = session_store.get_session(session_id)
        tool_schemas = workflow_registry.get_tool_schemas() if workflow_registry is not None else []
        decision = decide_next_step_fn(session.messages, session.slots, tool_schemas)

        slot_updates = decision.get("slot_updates", {})
        session_store.update_slots(session_id, **slot_updates)

        if decision["type"] == "assistant":
            session_store.append_message(session_id, "assistant", decision["message"])
            await emit_event(queue, {"type": "assistant", "message": decision["message"]})
            await emit_event(queue, {"type": "done"})
            return

        if decision.get("assistant_message"):
            session_store.append_message(session_id, "assistant", decision["assistant_message"])
            await emit_event(queue, {"type": "assistant", "message": decision["assistant_message"]})

        result = await workflow_registry.call_tool(decision["tool_name"], decision["arguments"], lambda payload: emit_event(queue, payload))
        artifact_event = build_artifact_event(result)
        await emit_event(queue, artifact_event)

        final_message = summarize_result_fn(decision["tool_name"], result)
        session_store.append_message(session_id, "assistant", final_message)
        await emit_event(queue, {"type": "assistant", "message": final_message})
        await emit_event(queue, {"type": "done"})
    finally:
        session_store.finish_run(session_id, run_id)
        runs.pop(run_id, None)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest test_agent_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_service.py test_agent_service.py
git commit -m "feat: refactor agent service for multi-turn sessions"
```

### Task 5: Upgrade FastAPI to Session-Based Routes and Streams

**Files:**
- Modify: `app.py`
- Modify: `test_app.py`

- [ ] **Step 1: Replace the old task-route tests with session-route tests**

```python
from threading import Event
from types import SimpleNamespace

import asyncio

from fastapi.testclient import TestClient

from app import create_app


def _make_run(run_id="run-123", session_id="session-123"):
    return SimpleNamespace(run_id=run_id, session_id=session_id, queue=asyncio.Queue())


def test_create_session_returns_session_id():
    class FakeSession:
        session_id = "session-123"

    test_app = create_app(new_session_fn=lambda: FakeSession())
    client = TestClient(test_app)

    response = client.post("/api/sessions")

    assert response.status_code == 200
    assert response.json() == {"session_id": "session-123"}


def test_get_session_returns_message_history_and_slots():
    test_app = create_app(
        get_session_payload_fn=lambda session_id: {
            "session_id": session_id,
            "messages": [{"role": "user", "content": "帮我看一下 Blackview 的竞品"}],
            "slots": {"platform": None, "brand": "Blackview", "count": None},
            "active_run_id": None,
        }
    )
    client = TestClient(test_app)

    response = client.get("/api/sessions/session-123")

    assert response.status_code == 200
    assert response.json()["slots"]["brand"] == "Blackview"


def test_post_message_returns_run_id_and_schedules_background_work():
    called = Event()
    run = _make_run()

    def fake_new_run(session_id, message):
        assert session_id == "session-123"
        assert message == "帮我看一下 Blackview 的竞品"
        return run

    async def fake_run_session_message(session_id, run_id, queue):
        assert session_id == "session-123"
        assert run_id == "run-123"
        assert queue is run.queue
        called.set()

    test_app = create_app(new_run_fn=fake_new_run, run_session_message_fn=fake_run_session_message)
    client = TestClient(test_app)

    response = client.post(
        "/api/sessions/session-123/messages",
        json={"message": "帮我看一下 Blackview 的竞品"},
    )

    assert response.status_code == 200
    assert response.json() == {"session_id": "session-123", "run_id": "run-123"}
    assert called.wait(1)


def test_stream_route_emits_assistant_and_done_frames():
    runs = {}
    run = _make_run(run_id="run-stream", session_id="session-123")
    runs[run.run_id] = run
    asyncio.run(run.queue.put({"type": "assistant", "message": "你想分析哪个平台？目前我支持 Amazon。"}))
    asyncio.run(run.queue.put({"type": "done"}))

    test_app = create_app(runs=runs)
    client = TestClient(test_app)

    response = client.get("/api/sessions/session-123/runs/run-stream/stream")

    assert response.status_code == 200
    assert 'data: {"type": "assistant", "message": "你想分析哪个平台？目前我支持 Amazon。"}\n\n' in response.text
    assert 'data: {"type": "done"}\n\n' in response.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest test_app.py -v`
Expected: FAIL because the new session routes and injected dependencies are not yet implemented

- [ ] **Step 3: Refactor `app.py` to expose session and run endpoints**

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent_service import RUNS, get_session_payload, new_run, new_session, run_session_message
from artifacts import ARTIFACTS_DIR


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
TERMINAL_EVENT_TYPES = {"done", "error"}


class MessageRequest(BaseModel):
    message: str


class SafeStaticFiles(StaticFiles):
    async def check_config(self) -> None:
        if self.directory and not Path(self.directory).exists():
            return
        await super().check_config()

    async def get_response(self, path: str, scope):
        if self.directory and not Path(self.directory).exists():
            return Response(status_code=404)
        return await super().get_response(path, scope)


def build_run_event_stream(run_id: str, run, runs: dict):
    async def event_stream():
        terminal_reached = False
        try:
            while True:
                payload = await run.queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if payload.get("type") in TERMINAL_EVENT_TYPES:
                    terminal_reached = True
                    break
        finally:
            if terminal_reached:
                runs.pop(run_id, None)

    return event_stream()


def create_app(
    *,
    frontend_dir: Path = FRONTEND_DIR,
    artifacts_dir: Path = ARTIFACTS_DIR,
    runs: dict = RUNS,
    new_session_fn=new_session,
    get_session_payload_fn=get_session_payload,
    new_run_fn=new_run,
    run_session_message_fn=run_session_message,
):
    app = FastAPI()
    app.mount(
        "/static",
        SafeStaticFiles(directory=str(frontend_dir), html=True, check_dir=False),
        name="static",
    )

    @app.get("/")
    async def index():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return HTMLResponse("<html><body><h1>竞品分析</h1></body></html>")

    @app.post("/api/sessions")
    async def create_session_route():
        session = new_session_fn()
        return {"session_id": session.session_id}

    @app.get("/api/sessions/{session_id}")
    async def get_session_route(session_id: str):
        try:
            return get_session_payload_fn(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    @app.post("/api/sessions/{session_id}/messages")
    async def post_message(session_id: str, request: MessageRequest):
        try:
            run = new_run_fn(session_id, request.message)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

        asyncio.create_task(run_session_message_fn(session_id, run.run_id, run.queue))
        return {"session_id": session_id, "run_id": run.run_id}

    @app.get("/api/sessions/{session_id}/runs/{run_id}/stream")
    async def stream_run(session_id: str, run_id: str):
        run = runs.get(run_id)
        if run is None or run.session_id != session_id:
            raise HTTPException(status_code=404, detail="Run not found")
        return StreamingResponse(
            build_run_event_stream(run_id, run, runs),
            media_type="text/event-stream",
        )

    @app.get("/api/download/{filename}")
    async def download_file(filename: str):
        if Path(filename).name != filename:
            raise HTTPException(status_code=404, detail="File not found")

        path = artifacts_dir / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(path, filename=filename)

    return app
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "feat: add session-based api routes"
```

### Task 6: Update the Frontend for Sessions and Mixed Assistant/Artifact Events

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `test_frontend_static.py`

- [ ] **Step 1: Write the failing frontend static tests**

```python
from pathlib import Path


def test_frontend_script_uses_session_routes_instead_of_chat_routes():
    script = Path("frontend/app.js").read_text(encoding="utf-8")

    assert 'fetch("/api/sessions"' in script
    assert "/messages" in script
    assert "/runs/" in script
    assert "/api/chat" not in script


def test_frontend_script_handles_mixed_agent_event_types():
    script = Path("frontend/app.js").read_text(encoding="utf-8")

    assert 'type === "assistant"' in script
    assert 'type === "tool_status"' in script
    assert 'type === "artifact"' in script
    assert 'type === "done"' in script


def test_index_page_uses_multi_turn_example_copy():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert "帮我看一下 Blackview 的竞品" in html
    assert "从亚马逊获取 Blackview 5 个竞品分析" not in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest test_frontend_static.py -v`
Expected: FAIL because the frontend still posts to `/api/chat` and still shows the one-shot example

- [ ] **Step 3: Update the frontend to create sessions and render mixed events**

```html
<!-- frontend/index.html -->
<div class="panel-heading">
  <h2>发起分析</h2>
  <p>示例：帮我看一下 Blackview 的竞品，然后补充 Amazon 和数量。</p>
</div>

<form id="chat-form" class="composer" novalidate>
  <label class="composer-label" for="message-input">对话内容</label>
  <textarea
    id="message-input"
    name="message"
    rows="4"
    placeholder="帮我看一下 Blackview 的竞品"
    required
  ></textarea>
  <div class="composer-actions">
    <p id="form-status" class="form-status" aria-live="polite">正在创建会话...</p>
    <button id="submit-button" type="submit">发送消息</button>
  </div>
</form>
```

```javascript
// frontend/app.js
"use strict";

(function () {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("message-input");
  const submitButton = document.getElementById("submit-button");
  const formStatus = document.getElementById("form-status");
  const messageList = document.getElementById("message-list");

  let activeSource = null;
  let sessionId = null;

  bootstrapSession();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = input.value.trim();
    if (!message || !sessionId) {
      return;
    }

    if (activeSource) {
      activeSource.close();
      activeSource = null;
    }

    appendUserMessage(message);
    setSubmitting(true);
    updateFormState("正在发送消息...", true);

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (!response.ok) {
        throw new Error("消息发送失败");
      }

      const payload = await response.json();
      openStream(payload.session_id, payload.run_id);
      input.value = "";
    } catch (error) {
      appendAssistantMessage({
        title: "Error",
        body: getErrorMessage(error),
        tone: "error",
      });
      updateFormState("消息发送失败。", false);
      setSubmitting(false);
    }
  });

  async function bootstrapSession() {
    try {
      const response = await fetch("/api/sessions", { method: "POST" });
      const payload = await response.json();
      sessionId = payload.session_id;
      updateFormState(`会话已创建：${sessionId}`, false);
    } catch (error) {
      updateFormState(getErrorMessage(error), false);
      submitButton.disabled = true;
    }
  }

  function openStream(currentSessionId, runId) {
    const source = new EventSource(
      `/api/sessions/${encodeURIComponent(currentSessionId)}/runs/${encodeURIComponent(runId)}/stream`
    );
    activeSource = source;

    source.onmessage = (event) => {
      const payload = parsePayload(event.data);
      if (!payload) {
        return;
      }
      renderPayload(payload);
      if (payload.type === "done" || payload.type === "error") {
        finalizeStream();
      }
    };

    source.onerror = () => {
      if (activeSource !== source) {
        return;
      }
      appendAssistantMessage({
        title: "Stream Error",
        body: "事件流已中断，请稍后重试。",
        tone: "error",
      });
      finalizeStream();
    };
  }

  function renderPayload(payload) {
    const type = payload.type;

    if (type === "assistant") {
      appendAssistantMessage({
        title: "Assistant",
        body: payload.message || "",
        tone: "assistant",
      });
      updateFormState(payload.message || "等待下一条消息。", false);
      return;
    }

    if (type === "tool_status") {
      appendAssistantMessage({
        title: "Status",
        body: payload.message || "工具执行中。",
        tone: "status",
      });
      updateFormState(payload.message || "工具执行中。", true);
      return;
    }

    if (type === "artifact") {
      const resultMessage = appendAssistantMessage({
        title: "Artifact",
        body: payload.summary || "结果已生成。",
        tone: "result",
      });
      if (payload.download_url) {
        resultMessage.appendChild(buildDownloadLink(payload.download_url, payload.filename));
      }
      if (Array.isArray(payload.preview_columns) && Array.isArray(payload.preview_rows)) {
        resultMessage.appendChild(buildPreviewTable(payload.preview_columns, payload.preview_rows));
      }
      return;
    }

    if (type === "error") {
      appendAssistantMessage({
        title: "Error",
        body: payload.message || "任务执行失败。",
        tone: "error",
      });
      updateFormState(payload.message || "任务执行失败。", false);
      return;
    }
  }
})();
```

```css
/* frontend/styles.css */
.form-status {
  min-height: 1.5rem;
}

.message.assistant .message-role {
  background: #e9f2ff;
}

.message.status .message-role {
  background: #fff4d6;
}

.message.result .message-role {
  background: #e7f8ee;
}

.message.error .message-role {
  background: #ffe8e6;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest test_frontend_static.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css test_frontend_static.py
git commit -m "feat: update frontend for session-based agent chat"
```
