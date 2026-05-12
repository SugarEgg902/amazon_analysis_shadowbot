# Python Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the formal Python runtime into a layered `mp_agent/` package and move formal tests into `tests/`, while keeping `uvicorn app:app --reload` and `pytest -q` working from repository root.

**Architecture:** Migrate in package-first stages. First create `mp_agent/` implementations for domain and infrastructure plus matching tests under `tests/`; then move application orchestration; then move the HTTP layer behind a thin root `app.py` shim; finally remove stale flat root modules once all formal tests target the package paths. This preserves a working repo after every task and avoids circular imports or broken monkeypatch targets.

**Tech Stack:** Python 3, FastAPI, asyncio, pytest, Playwright/Bright Data integrations, static HTML/CSS/JavaScript

---

## File Structure

**Create:**
- `mp_agent/__init__.py`
- `mp_agent/presentation/__init__.py`
- `mp_agent/presentation/http.py`
- `mp_agent/application/__init__.py`
- `mp_agent/application/agent_service.py`
- `mp_agent/domain/__init__.py`
- `mp_agent/domain/analysis.py`
- `mp_agent/infrastructure/__init__.py`
- `mp_agent/infrastructure/amazon.py`
- `mp_agent/infrastructure/artifacts.py`
- `tests/presentation/test_app.py`
- `tests/application/test_agent_service.py`
- `tests/domain/test_analysis.py`
- `tests/infrastructure/test_artifacts.py`
- `tests/infrastructure/test_amazon.py`
- `tests/ui/test_frontend_static.py`
- `docs/superpowers/plans/2026-05-11-python-layering.md`

**Modify:**
- `app.py`
- `agent_service.py`

**Delete:**
- `analysis_tools.py`
- `artifacts.py`
- `amazon_tools.py`
- `agent_service.py`
- `test_analysis_tools.py`
- `test_artifacts.py`
- `test_amazon_tools.py`
- `test_agent_service.py`
- `test_app.py`
- `test_frontend_static.py`

**Keep Unchanged:**
- `temp_if_use/`
- `frontend/`

**Responsibilities:**
- `mp_agent/presentation/http.py`: FastAPI app factory, routes, SSE stream helpers, static file serving
- `mp_agent/application/agent_service.py`: task parsing, orchestration, progress/result payload emission
- `mp_agent/domain/analysis.py`: row-building logic and analysis helpers
- `mp_agent/infrastructure/amazon.py`: Amazon scraping and review-summary integrations
- `mp_agent/infrastructure/artifacts.py`: artifact path and CSV writing
- `app.py`: root compatibility shim only

### Task 1: Create the Package Skeleton and Move Domain/Infrastructure Tests First

**Files:**
- Create: `mp_agent/__init__.py`
- Create: `mp_agent/domain/__init__.py`
- Create: `mp_agent/domain/analysis.py`
- Create: `mp_agent/infrastructure/__init__.py`
- Create: `mp_agent/infrastructure/artifacts.py`
- Create: `mp_agent/infrastructure/amazon.py`
- Create: `tests/domain/test_analysis.py`
- Create: `tests/infrastructure/test_artifacts.py`
- Create: `tests/infrastructure/test_amazon.py`
- Delete: `test_analysis_tools.py`
- Delete: `test_artifacts.py`
- Delete: `test_amazon_tools.py`

- [ ] **Step 1: Write the failing package-path tests**

Create the package-path test files by moving the current root tests and changing only the imports:

```python
# tests/domain/test_analysis.py
from mp_agent.domain.analysis import build_analysis_row
```

```python
# tests/infrastructure/test_artifacts.py
from datetime import datetime

import mp_agent.infrastructure.artifacts as artifacts
from mp_agent.infrastructure.artifacts import ARTIFACTS_DIR, CSV_COLUMNS, write_analysis_csv
```

```python
# tests/infrastructure/test_amazon.py
import asyncio
import sys
import types

import pytest

from mp_agent.infrastructure import amazon as amazon_tools
```

Move the rest of each original file body over unchanged, then delete the root test files they replaced.

- [ ] **Step 2: Run the moved tests to verify they fail**

Run: `python3 -m pytest tests/domain/test_analysis.py tests/infrastructure/test_artifacts.py tests/infrastructure/test_amazon.py -k "not summarize_reviews_uses_excel_flow_and_summarizes" -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mp_agent'`

- [ ] **Step 3: Write the minimal package implementation for domain and infrastructure**

Create the package skeleton:

```python
# mp_agent/__init__.py
"""Formal runtime package for layered application code."""
```

```python
# mp_agent/domain/__init__.py
"""Domain-layer modules."""
```

```python
# mp_agent/infrastructure/__init__.py
"""Infrastructure-layer modules."""
```

Copy the full current implementation files into their package destinations:

- copy `analysis_tools.py` -> `mp_agent/domain/analysis.py`
- copy `artifacts.py` -> `mp_agent/infrastructure/artifacts.py`
- copy `amazon_tools.py` -> `mp_agent/infrastructure/amazon.py`

Do not delete the root runtime files yet. The package copies become the new source of truth for tests, but the old root files remain temporarily so the current app path keeps working while later tasks migrate the orchestrator and HTTP layer.

- [ ] **Step 4: Run the moved tests to verify they pass**

Run: `python3 -m pytest tests/domain/test_analysis.py tests/infrastructure/test_artifacts.py tests/infrastructure/test_amazon.py -k "not summarize_reviews_uses_excel_flow_and_summarizes" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mp_agent/__init__.py mp_agent/domain/__init__.py mp_agent/domain/analysis.py mp_agent/infrastructure/__init__.py mp_agent/infrastructure/artifacts.py mp_agent/infrastructure/amazon.py tests/domain/test_analysis.py tests/infrastructure/test_artifacts.py tests/infrastructure/test_amazon.py
git rm test_analysis_tools.py test_artifacts.py test_amazon_tools.py
git commit -m "refactor: add layered domain and infrastructure package"
```

### Task 2: Move the Application Layer and Repoint It to Package Imports

**Files:**
- Create: `mp_agent/application/__init__.py`
- Create: `mp_agent/application/agent_service.py`
- Create: `tests/application/test_agent_service.py`
- Modify: `agent_service.py`
- Delete: `test_agent_service.py`

- [ ] **Step 1: Write the failing application-layer test move**

Move `test_agent_service.py` to `tests/application/test_agent_service.py` and change the imports to package paths:

```python
from mp_agent.application.agent_service import PREVIEW_COLUMNS, TASKS, new_task, parse_competitor_request, run_task
```

Keep the rest of the file body unchanged, then delete the root `test_agent_service.py`.

- [ ] **Step 2: Run the application tests to verify they fail**

Run: `python3 -m pytest tests/application/test_agent_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mp_agent.application'`

- [ ] **Step 3: Write the minimal application-layer implementation and compatibility shim**

Create the package init:

```python
# mp_agent/application/__init__.py
"""Application-layer orchestration modules."""
```

Copy the current `agent_service.py` implementation into `mp_agent/application/agent_service.py`, then change its imports to the package modules:

```python
from mp_agent.domain.analysis import build_analysis_row
from mp_agent.infrastructure.amazon import scrape_amazon_products, summarize_reviews
from mp_agent.infrastructure.artifacts import write_analysis_csv
```

Replace the root `agent_service.py` with a temporary compatibility shim:

```python
from mp_agent.application.agent_service import (
    PREVIEW_COLUMNS,
    TASKS,
    AgentTask,
    emit_event,
    new_task,
    parse_competitor_request,
    run_task,
)

__all__ = [
    "PREVIEW_COLUMNS",
    "TASKS",
    "AgentTask",
    "emit_event",
    "new_task",
    "parse_competitor_request",
    "run_task",
]
```

This shim is temporary and exists only to keep the current root `app.py` import path stable until Task 3 moves the HTTP layer.

- [ ] **Step 4: Run the application tests to verify they pass**

Run: `python3 -m pytest tests/application/test_agent_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mp_agent/application/__init__.py mp_agent/application/agent_service.py agent_service.py tests/application/test_agent_service.py
git rm test_agent_service.py
git commit -m "refactor: move agent service into application layer"
```

### Task 3: Move the HTTP Layer Behind the Root Entry Shim

**Files:**
- Create: `mp_agent/presentation/__init__.py`
- Create: `mp_agent/presentation/http.py`
- Create: `tests/presentation/test_app.py`
- Modify: `app.py`
- Delete: `test_app.py`

- [ ] **Step 1: Write the failing presentation-layer test move**

Move `test_app.py` to `tests/presentation/test_app.py` and update its imports so the real implementation comes from the package:

```python
from mp_agent.presentation.http import ARTIFACTS_DIR, app, build_task_event_stream, create_app
from mp_agent.infrastructure.artifacts import ARTIFACTS_DIR as SHARED_ARTIFACTS_DIR
```

Add one explicit compatibility assertion for the root shim:

```python
from app import app as root_app


def test_root_app_shim_exports_same_app():
    assert root_app is app
```

Delete the root `test_app.py` after the new test file is in place.

- [ ] **Step 2: Run the presentation tests to verify they fail**

Run: `python3 -m pytest tests/presentation/test_app.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mp_agent.presentation'`

- [ ] **Step 3: Write the minimal presentation implementation and root shim**

Create the package init:

```python
# mp_agent/presentation/__init__.py
"""Presentation-layer modules."""
```

Move the current HTTP implementation from root `app.py` into `mp_agent/presentation/http.py` and change imports to package paths:

```python
from mp_agent.application.agent_service import TASKS, new_task, run_task
from mp_agent.infrastructure.artifacts import ARTIFACTS_DIR
```

Update repo-root `app.py` to a thin shim:

```python
from mp_agent.presentation.http import ARTIFACTS_DIR, app, build_task_event_stream, create_app

__all__ = ["ARTIFACTS_DIR", "app", "build_task_event_stream", "create_app"]
```

When moving the HTTP code, preserve the repo-root path calculations by making `BASE_DIR` point two levels up from `mp_agent/presentation/http.py`:

```python
BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
```

- [ ] **Step 4: Run the presentation tests to verify they pass**

Run: `python3 -m pytest tests/presentation/test_app.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mp_agent/presentation/__init__.py mp_agent/presentation/http.py app.py tests/presentation/test_app.py
git rm test_app.py
git commit -m "refactor: move HTTP app into presentation layer"
```

### Task 4: Move the Remaining Formal Test File and Finish Package-Path Test Discovery

**Files:**
- Create: `tests/ui/test_frontend_static.py`
- Delete: `test_frontend_static.py`

- [ ] **Step 1: Write the failing UI test move**

Move `test_frontend_static.py` to `tests/ui/test_frontend_static.py` without changing the file body. The file already reads `frontend/index.html` and `frontend/app.js` by path, so it should not require import rewrites.

- [ ] **Step 2: Run the UI tests to verify the moved path works**

Run: `python3 -m pytest tests/ui/test_frontend_static.py -q`
Expected: PASS

- [ ] **Step 3: Verify root-level pytest discovery no longer depends on root test files**

Run this combined check after deleting the root UI test:

```bash
python3 -m pytest tests/domain/test_analysis.py tests/infrastructure/test_artifacts.py tests/application/test_agent_service.py tests/presentation/test_app.py tests/ui/test_frontend_static.py -q
```

Expected: PASS

- [ ] **Step 4: Delete the root UI test file**

Run:

```bash
git rm test_frontend_static.py
```

No code block change is needed here because the test body was moved unchanged in Step 1.

- [ ] **Step 5: Commit**

```bash
git add tests/ui/test_frontend_static.py
git commit -m "test: move formal frontend static test under tests tree"
```

### Task 5: Remove the Stale Flat Runtime Modules and Run Final Verification

**Files:**
- Modify: `mp_agent/presentation/http.py`
- Modify: `mp_agent/infrastructure/artifacts.py`
- Delete: `analysis_tools.py`
- Delete: `artifacts.py`
- Delete: `amazon_tools.py`
- Delete: `agent_service.py`

- [ ] **Step 1: Write the final compatibility guard**

Add one assertion to `tests/presentation/test_app.py` that importing through root `app.py` still exposes the public entry symbols:

```python
from app import ARTIFACTS_DIR as root_artifacts_dir
from app import build_task_event_stream as root_build_task_event_stream
from app import create_app as root_create_app


def test_root_app_shim_exports_public_http_symbols():
    assert root_artifacts_dir == ARTIFACTS_DIR
    assert root_build_task_event_stream is build_task_event_stream
    assert root_create_app is create_app
```

- [ ] **Step 2: Run the compatibility test to verify it fails if the shim is incomplete**

Run: `python3 -m pytest tests/presentation/test_app.py -k root_app_shim -q`
Expected: PASS if Task 3 already completed correctly; if it fails, fix the shim before deleting any flat root modules.

- [ ] **Step 3: Remove the obsolete flat runtime files**

Delete the old flat runtime modules now that the package modules and package-based tests are in place:

```bash
git rm analysis_tools.py artifacts.py amazon_tools.py agent_service.py
```

Do not delete root `app.py`. It remains the only intentional root runtime compatibility file.

- [ ] **Step 4: Run final verification**

Run:

```bash
python3 -m pytest tests/domain/test_analysis.py tests/infrastructure/test_artifacts.py tests/infrastructure/test_amazon.py tests/application/test_agent_service.py tests/presentation/test_app.py tests/ui/test_frontend_static.py -k "not summarize_reviews_uses_excel_flow_and_summarizes" -q
python3 -m pytest -q
python3 -c "from app import app, create_app"
```

Expected:
- the focused layered test command PASSes
- `python3 -c "from app import app, create_app"` exits 0
- the full `pytest -q` run preserves the current known unrelated failure `test_summarize_reviews_uses_excel_flow_and_summarizes` unless that test has been fixed separately during implementation

- [ ] **Step 5: Commit**

```bash
git add mp_agent/presentation/http.py mp_agent/infrastructure/artifacts.py tests/presentation/test_app.py
git commit -m "refactor: remove flat runtime modules after package migration"
```

## Self-Review

Spec coverage check:

- layered runtime package: covered by Tasks 1 to 3
- layered test tree: covered by Tasks 1 to 4
- root entry compatibility: covered by Tasks 3 and 5
- dependency direction discipline: covered by package import rewrites in Tasks 2 and 3
- leave `temp_if_use/` alone: preserved throughout all tasks

Placeholder scan:

- no `TODO` or `TBD`
- all tasks contain exact files, commands, and code snippets

Type/import consistency:

- package names are consistently `mp_agent.presentation.http`, `mp_agent.application.agent_service`, `mp_agent.domain.analysis`, and `mp_agent.infrastructure.{amazon,artifacts}`
- only root `app.py` survives as a runtime shim in the final state
