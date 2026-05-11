# Excel Review Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch `summarize_reviews` from API-based review retrieval to overwrite-one-URL Excel input plus poll-and-read-once Excel output.

**Architecture:** Add minimal XLSX helpers inside `amazon_tools.py` so the workflow can write `asin_list.xlsx` and read `all_reviews.xlsx` without external dependencies. Keep the existing summary pipeline after review rows are loaded.

**Tech Stack:** Python stdlib, ZIP/XML parsing, pytest

---

### Task 1: Lock the New Workflow with Tests

**Files:**
- Modify: `test_amazon_tools.py`
- Test: `test_amazon_tools.py`

- [ ] **Step 1: Write the failing test**

Add a test that stubs workbook write/read helpers and asserts `summarize_reviews()` overwrites the source workbook, polls until data exists, then summarizes the loaded review rows.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_amazon_tools.py -k excel`
Expected: FAIL because the current implementation still uses the Bright Data path.

- [ ] **Step 3: Write minimal implementation**

Implement Excel write, poll, and read helpers plus a new `summarize_reviews()` data path that uses them.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_amazon_tools.py -k excel`
Expected: PASS

### Task 2: Preserve Summary Behavior

**Files:**
- Modify: `amazon_tools.py`
- Test: `test_amazon_tools.py`

- [ ] **Step 1: Reuse existing review bucketing**

Keep positive, negative, and neutral review classification based on the loaded review rows.

- [ ] **Step 2: Reuse local LLM summary**

Normalize loaded rows into the existing `pros`/`cons`/`overall` summary input shape.

- [ ] **Step 3: Run focused verification**

Run: `python3 -m pytest test_amazon_tools.py`
Expected: PASS
