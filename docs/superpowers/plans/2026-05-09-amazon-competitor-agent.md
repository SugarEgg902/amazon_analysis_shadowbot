# Amazon Competitor Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI + static SPA agent that parses Amazon competitor-analysis requests, streams progress with SSE, calls the Amazon scraping/review tools plus a dedicated analysis tool, and returns a downloadable CSV link in the chat UI.

**Architecture:** Keep orchestration in a small backend service layer that creates per-task event streams, leaving `amazon_tools.py` as the Amazon tool boundary. Add a separate analysis tool for product-level competitor reasoning, a CSV artifact helper, and a minimal static frontend that only displays streamed messages and the final download link.

**Tech Stack:** Python 3, FastAPI, Uvicorn, OpenAI-compatible client, pytest, static HTML/CSS/JavaScript, CSV from Python stdlib

---

## File Structure

**Create:**
- `requirements.txt`
- `app.py`
- `agent_service.py`
- `analysis_tools.py`
- `artifacts.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `test_app.py`
- `test_agent_service.py`
- `test_analysis_tools.py`
- `test_artifacts.py`

**Modify:**
- `amazon_tools.py`

**Responsibilities:**
- `requirements.txt`: runtime and test dependency list for this repo
- `app.py`: FastAPI app, static mount, task creation route, SSE route, file download route
- `agent_service.py`: prompt parsing, task registry, SSE event generator, orchestration of the three tools
- `analysis_tools.py`: local LLM competitor-analysis tool that returns the fixed CSV schema
- `artifacts.py`: CSV writing helpers and download metadata
- `frontend/index.html`: SPA shell
- `frontend/app.js`: submit prompt, open SSE stream, render status/item/result/error messages
- `frontend/styles.css`: lightweight layout and chat styling
- `test_app.py`: API and SSE contract tests
- `test_agent_service.py`: parser and orchestration tests
- `test_analysis_tools.py`: analysis tool contract tests
- `test_artifacts.py`: CSV schema and filename tests
- `amazon_tools.py`: expose a small tool wrapper if needed so the agent service can import tools cleanly

### Task 1: Create Runtime Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `test_app.py`

- [ ] **Step 1: Write the failing dependency and app import test**

```python
from pathlib import Path


def test_requirements_lists_fastapi_stack():
    text = Path("requirements.txt").read_text(encoding="utf-8")

    assert "fastapi" in text
    assert "uvicorn" in text
    assert "openai" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_app.py::test_requirements_lists_fastapi_stack -v`
Expected: FAIL with `FileNotFoundError` because `requirements.txt` does not exist yet

- [ ] **Step 3: Write minimal runtime scaffold**

```text
fastapi
uvicorn
openai
pytest
```

Save that content to `requirements.txt`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_app.py::test_requirements_lists_fastapi_stack -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt test_app.py
git commit -m "chore: add fastapi runtime scaffold"
```

### Task 2: Add Prompt Parsing and Task Registry

**Files:**
- Create: `agent_service.py`
- Create: `test_agent_service.py`

- [ ] **Step 1: Write the failing parser tests**

```python
from agent_service import parse_competitor_request


def test_parse_competitor_request_extracts_brand_and_count():
    parsed = parse_competitor_request("从亚马逊获取 Blackview 5 个竞品分析")

    assert parsed == {
        "platform": "amazon",
        "brand": "Blackview",
        "count": 5,
    }


def test_parse_competitor_request_rejects_invalid_prompt():
    parsed = parse_competitor_request("帮我看看这个品牌")

    assert parsed is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_agent_service.py::test_parse_competitor_request_extracts_brand_and_count test_agent_service.py::test_parse_competitor_request_rejects_invalid_prompt -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service'`

- [ ] **Step 3: Write minimal parser and task types**

```python
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass

TASKS: dict[str, "AgentTask"] = {}


@dataclass
class AgentTask:
    task_id: str
    message: str
    queue: asyncio.Queue


def parse_competitor_request(message: str) -> dict | None:
    text = (message or "").strip()
    if "亚马逊" not in text:
        return None

    match = re.search(r"从亚马逊获取\s+(.+?)\s+(\d+)\s*个竞品分析", text)
    if not match:
        return None

    brand = match.group(1).strip()
    count = int(match.group(2))
    if not brand or count <= 0:
        return None

    return {
        "platform": "amazon",
        "brand": brand,
        "count": count,
    }


def new_task(message: str) -> AgentTask:
    return AgentTask(
        task_id=uuid.uuid4().hex,
        message=message,
        queue=asyncio.Queue(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_agent_service.py::test_parse_competitor_request_extracts_brand_and_count test_agent_service.py::test_parse_competitor_request_rejects_invalid_prompt -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_service.py test_agent_service.py
git commit -m "feat: add prompt parser and task registry"
```

### Task 3: Add the Competitor Analysis Tool

**Files:**
- Create: `analysis_tools.py`
- Create: `test_analysis_tools.py`

- [ ] **Step 1: Write the failing analysis tool contract test**

```python
from analysis_tools import build_analysis_row


def test_build_analysis_row_returns_required_columns(monkeypatch):
    def fake_llm(_payload):
        return {
            "核心卖点": "三防机身，长续航",
            "优点评炼": "续航长，机身耐用",
            "缺点评炼": "外观偏厚重",
            "综合分析": "适合户外和耐用场景",
            "竞品定位": "中低价三防竞品",
        }

    row = build_analysis_row(
        brand="Blackview",
        product={
            "asin": "B0TEST1234",
            "url": "https://www.amazon.com/dp/B0TEST1234",
            "title": "Blackview Example",
            "price": "$199.99",
            "rating": "4.4 out of 5 stars",
            "review_count": "321",
        },
        review_summary={
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        },
        llm_call=fake_llm,
    )

    assert row["品牌"] == "Blackview"
    assert row["ASIN"] == "B0TEST1234"
    assert row["url"] == "https://www.amazon.com/dp/B0TEST1234"
    assert row["商品标题"] == "Blackview Example"
    assert row["竞品定位"] == "中低价三防竞品"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_analysis_tools.py::test_build_analysis_row_returns_required_columns -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis_tools'`

- [ ] **Step 3: Write minimal analysis tool**

```python
from __future__ import annotations

import json
from openai import OpenAI


LLM_BASE_URL = "http://10.0.0.21:8005/v1"
LLM_MODEL = "gemma-4-31b-it-fp8"


def _default_llm_call(payload: dict) -> dict:
    client = OpenAI(base_url=LLM_BASE_URL, api_key="EMPTY")
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": "你是竞品分析助手，只输出 JSON。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content or "{}")


def build_analysis_row(brand: str, product: dict, review_summary: dict, llm_call=None) -> dict:
    llm_call = llm_call or _default_llm_call
    analysis = llm_call(
        {
            "brand": brand,
            "product": product,
            "review_summary": review_summary,
        }
    )
    return {
        "品牌": brand,
        "ASIN": product.get("asin", ""),
        "url": product.get("url", ""),
        "商品标题": product.get("title", ""),
        "价格": product.get("price", ""),
        "评分": product.get("rating", ""),
        "评论数": product.get("review_count", ""),
        "核心卖点": analysis.get("核心卖点", ""),
        "优点评炼": analysis.get("优点评炼", ""),
        "缺点评炼": analysis.get("缺点评炼", ""),
        "综合分析": analysis.get("综合分析", ""),
        "竞品定位": analysis.get("竞品定位", ""),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_analysis_tools.py::test_build_analysis_row_returns_required_columns -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add analysis_tools.py test_analysis_tools.py
git commit -m "feat: add competitor analysis tool"
```

### Task 4: Add CSV Artifact Helpers

**Files:**
- Create: `artifacts.py`
- Create: `test_artifacts.py`

- [ ] **Step 1: Write the failing CSV schema test**

```python
from artifacts import CSV_COLUMNS, write_analysis_csv


def test_write_analysis_csv_uses_expected_header_order(tmp_path):
    path = write_analysis_csv(
        rows=[
            {
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
        ],
        brand="Blackview",
        count=1,
        output_dir=tmp_path,
    )

    text = path.read_text(encoding="utf-8")

    assert CSV_COLUMNS[0] == "品牌"
    assert CSV_COLUMNS[2] == "url"
    assert text.splitlines()[0].startswith("品牌,ASIN,url,商品标题")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_artifacts.py::test_write_analysis_csv_uses_expected_header_order -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'artifacts'`

- [ ] **Step 3: Write minimal artifact helper**

```python
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


CSV_COLUMNS = [
    "品牌",
    "ASIN",
    "url",
    "商品标题",
    "价格",
    "评分",
    "评论数",
    "核心卖点",
    "优点评炼",
    "缺点评炼",
    "综合分析",
    "竞品定位",
]


def write_analysis_csv(rows: list[dict], brand: str, count: int, output_dir="artifacts") -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"amazon_{brand.lower()}_{count}_{timestamp}.csv"

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})

    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_artifacts.py::test_write_analysis_csv_uses_expected_header_order -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add artifacts.py test_artifacts.py
git commit -m "feat: add csv artifact writer"
```

### Task 5: Implement the Orchestration Loop

**Files:**
- Modify: `agent_service.py`
- Modify: `test_agent_service.py`
- Modify: `amazon_tools.py`

- [ ] **Step 1: Write the failing orchestration test**

```python
import asyncio

from agent_service import run_task


def test_run_task_emits_status_item_and_result(monkeypatch, tmp_path):
    events = []

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [
            {
                "asin": "B0TEST1234",
                "url": "https://www.amazon.com/dp/B0TEST1234",
                "title": "Blackview Example",
                "price": "$199.99",
                "rating": "4.4 out of 5 stars",
                "review_count": "321",
                "bullets": ["Rugged", "Long battery"],
            }
        ]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row(**kwargs):
        return {
            "品牌": kwargs["brand"],
            "ASIN": kwargs["product"]["asin"],
            "url": kwargs["product"]["url"],
            "商品标题": kwargs["product"]["title"],
            "价格": kwargs["product"]["price"],
            "评分": kwargs["product"]["rating"],
            "评论数": kwargs["product"]["review_count"],
            "核心卖点": "三防机身",
            "优点评炼": "续航长",
            "缺点评炼": "偏厚重",
            "综合分析": "适合户外",
            "竞品定位": "中低价三防竞品",
        }

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)
    monkeypatch.setattr("agent_service.summarize_reviews", fake_reviews)
    monkeypatch.setattr("agent_service.build_analysis_row", fake_row)
    monkeypatch.setattr("agent_service.write_analysis_csv", lambda rows, brand, count: tmp_path / "out.csv")

    asyncio.run(run_task("从亚马逊获取 Blackview 1 个竞品分析", asyncio.Queue()))

    assert events[0]["type"] == "status"
    assert any(event["type"] == "item" for event in events)
    assert events[-1]["type"] == "result"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_agent_service.py::test_run_task_emits_status_item_and_result -v`
Expected: FAIL because `run_task` and `emit_event` do not exist yet

- [ ] **Step 3: Write minimal orchestration loop**

```python
from amazon_tools import scrape_amazon_products, summarize_reviews
from analysis_tools import build_analysis_row
from artifacts import write_analysis_csv, CSV_COLUMNS


async def emit_event(queue: asyncio.Queue, payload: dict) -> None:
    await queue.put(payload)


async def run_task(message: str, queue: asyncio.Queue) -> None:
    parsed = parse_competitor_request(message)
    if parsed is None:
        await emit_event(queue, {"type": "error", "message": "请输入品牌和数量，例如：从亚马逊获取 Blackview 5 个竞品分析"})
        return

    brand = parsed["brand"]
    count = parsed["count"]
    await emit_event(queue, {"type": "status", "message": "正在抓取 Amazon 商品..."})
    products = await scrape_amazon_products(brand, max_valid=count)
    if not products:
        await emit_event(queue, {"type": "error", "message": "没有抓取到有效商品"})
        return

    rows = []
    for product in products:
        await emit_event(queue, {"type": "status", "message": f"正在分析 {product.get('asin', '')} ..."})
        try:
            review_summary = await summarize_reviews(product["asin"])
            row = build_analysis_row(brand=brand, product=product, review_summary=review_summary)
            rows.append(row)
            await emit_event(queue, {"type": "item", "asin": product["asin"], "title": product.get("title", ""), "row": row})
        except Exception as exc:
            await emit_event(queue, {"type": "status", "message": f"{product.get('asin', '')} 评论或分析失败: {exc}"})

    if not rows:
        await emit_event(queue, {"type": "error", "message": "没有生成有效竞品分析结果"})
        return

    csv_path = write_analysis_csv(rows, brand=brand, count=count)
    await emit_event(
        queue,
        {
            "type": "result",
            "summary": f"已完成 {len(rows)} 个竞品分析",
            "preview_columns": CSV_COLUMNS,
            "preview_rows": [[row.get(col, "") for col in CSV_COLUMNS] for row in rows],
            "download_url": f"/api/download/{csv_path.name}",
            "filename": csv_path.name,
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_agent_service.py::test_run_task_emits_status_item_and_result -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_service.py test_agent_service.py amazon_tools.py
git commit -m "feat: add amazon competitor orchestration loop"
```

### Task 6: Build the FastAPI App and SSE Route

**Files:**
- Create: `app.py`
- Modify: `test_app.py`

- [ ] **Step 1: Write the failing API contract tests**

```python
from fastapi.testclient import TestClient

from app import app


def test_create_chat_task_returns_task_id():
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "从亚马逊获取 Blackview 1 个竞品分析"})

    assert response.status_code == 200
    assert "task_id" in response.json()


def test_download_route_returns_404_for_missing_file():
    client = TestClient(app)

    response = client.get("/api/download/missing.csv")

    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_app.py::test_create_chat_task_returns_task_id test_app.py::test_download_route_returns_404_for_missing_file -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Write minimal FastAPI app**

```python
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json

from agent_service import TASKS, new_task, run_task


class ChatRequest(BaseModel):
    message: str


app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return Path("frontend/index.html").read_text(encoding="utf-8")


@app.post("/api/chat")
async def create_chat(request: ChatRequest) -> dict:
    task = new_task(request.message)
    TASKS[task.task_id] = task
    asyncio.create_task(run_task(request.message, task.queue))
    return {"task_id": task.task_id}


@app.get("/api/chat/{task_id}/stream")
async def stream_chat(task_id: str):
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def event_source():
        while True:
            payload = await task.queue.get()
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if payload["type"] in {"result", "error"}:
                break

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/api/download/{filename}")
def download(filename: str):
    path = Path("artifacts") / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, media_type="text/csv", filename=filename)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_app.py::test_create_chat_task_returns_task_id test_app.py::test_download_route_returns_404_for_missing_file -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "feat: add fastapi app and sse endpoints"
```

### Task 7: Add the Static Frontend

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/app.js`
- Create: `frontend/styles.css`

- [ ] **Step 1: Write the failing frontend contract test**

Add this simple server-side assertion in `test_app.py`:

```python
from pathlib import Path


def test_frontend_files_exist():
    assert Path("frontend/index.html").exists()
    assert Path("frontend/app.js").exists()
    assert Path("frontend/styles.css").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_app.py::test_frontend_files_exist -v`
Expected: FAIL because the `frontend/` files do not exist yet

- [ ] **Step 3: Write minimal frontend**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>竞品分析 Agent</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <main class="app">
      <section id="messages" class="messages"></section>
      <form id="chat-form" class="composer">
        <input id="message-input" placeholder="从亚马逊获取 Blackview 5 个竞品分析" />
        <button type="submit">发送</button>
      </form>
    </main>
    <script src="/static/app.js"></script>
  </body>
</html>
```

```javascript
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const messages = document.getElementById("messages");

function addMessage(role, text, extraHtml = "") {
  const el = document.createElement("article");
  el.className = `message ${role}`;
  el.innerHTML = `<div class="bubble"><p>${text}</p>${extraHtml}</div>`;
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
}

function renderResult(payload) {
  const header = payload.preview_columns.map((col) => `<th>${col}</th>`).join("");
  const rows = payload.preview_rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("");
  addMessage(
    "assistant",
    payload.summary,
    `<a href="${payload.download_url}" target="_blank">下载 ${payload.filename}</a><table><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>`
  );
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  addMessage("user", message);
  input.value = "";

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({message}),
  });
  const {task_id} = await response.json();
  const source = new EventSource(`/api/chat/${task_id}/stream`);

  source.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "status") addMessage("assistant", payload.message);
    if (payload.type === "item") addMessage("assistant", `已完成 ${payload.asin} 分析`);
    if (payload.type === "result") {
      renderResult(payload);
      source.close();
    }
    if (payload.type === "error") {
      addMessage("assistant", payload.message);
      source.close();
    }
  };
});
```

```css
body { margin: 0; font-family: sans-serif; background: #f5f3ee; color: #1f1f1f; }
.app { max-width: 960px; margin: 0 auto; padding: 24px; }
.messages { min-height: 70vh; display: flex; flex-direction: column; gap: 12px; }
.message .bubble { background: white; border-radius: 12px; padding: 12px 14px; }
.message.user .bubble { background: #dbeafe; }
.composer { display: flex; gap: 12px; margin-top: 20px; }
.composer input { flex: 1; padding: 12px; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { border: 1px solid #ddd; padding: 8px; font-size: 12px; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_app.py::test_frontend_files_exist -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css test_app.py
git commit -m "feat: add static chat frontend"
```

### Task 8: Verify the Full Contract

**Files:**
- Modify: `test_app.py`
- Modify: `test_agent_service.py`

- [ ] **Step 1: Add the SSE happy-path test**

```python
import asyncio

from fastapi.testclient import TestClient

from app import app


def test_stream_route_emits_result(monkeypatch):
    async def fake_run_task(_message, queue):
        await queue.put({"type": "status", "message": "start"})
        await queue.put({"type": "result", "summary": "done", "preview_columns": [], "preview_rows": [], "download_url": "/api/download/x.csv", "filename": "x.csv"})

    monkeypatch.setattr("app.run_task", fake_run_task)
    client = TestClient(app)
    create = client.post("/api/chat", json={"message": "从亚马逊获取 Blackview 1 个竞品分析"})
    task_id = create.json()["task_id"]

    with client.stream("GET", f"/api/chat/{task_id}/stream") as response:
        body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert b"status" in body
    assert b"result" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_app.py::test_stream_route_emits_result -v`
Expected: FAIL until the app and queue lifecycle line up with the stream test

- [ ] **Step 3: Make the smallest contract fixes**

If the stream test fails because of missing imports or task lifetime issues, apply only these minimal fixes:

```python
# app.py
import json


@app.post("/api/chat")
async def create_chat(request: ChatRequest) -> dict:
    task = new_task(request.message)
    TASKS[task.task_id] = task
    asyncio.create_task(run_task(request.message, task.queue))
    return {"task_id": task.task_id}


@app.get("/api/chat/{task_id}/stream")
async def stream_chat(task_id: str):
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def event_source():
        while True:
            payload = await task.queue.get()
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\\n\\n"
            if payload["type"] in {"result", "error"}:
                TASKS.pop(task_id, None)
                break

    return StreamingResponse(event_source(), media_type="text/event-stream")
```

- [ ] **Step 4: Run full targeted verification**

Run: `python3 -m pytest test_app.py test_agent_service.py test_analysis_tools.py test_artifacts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py agent_service.py analysis_tools.py artifacts.py test_app.py test_agent_service.py test_analysis_tools.py test_artifacts.py
git commit -m "test: verify competitor agent contract end to end"
```

## Self-Review

### Spec coverage

- FastAPI backend: covered by Tasks 1, 6, and 8
- static SPA frontend: covered by Task 7
- SSE streaming: covered by Tasks 5, 6, and 8
- Amazon tools `scrape_amazon_products` and `summarize_reviews`: covered by Task 5
- separate analysis tool: covered by Task 3
- CSV download link in chat UI: covered by Tasks 4, 6, and 7
- local model `http://10.0.0.21:8005` and `gemma-4-31b-it-fp8`: covered by Task 3
- fixed CSV columns including `url`: covered by Tasks 3 and 4
- per-item degradation and final error rules: covered by Task 5

### Placeholder scan

No `TODO`, `TBD`, or “implement later” placeholders remain.

### Type consistency

- Parser output is consistently `platform`, `brand`, `count`
- SSE event types are consistently `status`, `item`, `result`, `error`
- CSV field names match the design doc and artifact helper
- Analysis tool output keys match CSV schema and frontend preview usage
