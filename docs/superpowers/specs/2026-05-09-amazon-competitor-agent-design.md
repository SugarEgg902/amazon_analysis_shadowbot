# Amazon Competitor Agent Design

## Goal

Build a local agent experience for competitor analysis with:

- FastAPI backend
- static single-page frontend
- SSE streaming updates
- Amazon-specific tool orchestration for now
- CSV export with a download link shown inside the chat message list

The local LLM endpoint for orchestration and analysis is `http://10.0.0.21:8005`, using model `gemma-4-31b-it-fp8`.

## User Experience

The user opens a local web page and sends a request such as:

`从亚马逊获取 Blackview 5 个竞品分析`

The UI behaves like a lightweight chat agent:

- the user message is appended to the message list
- the backend starts streaming progress immediately
- intermediate status messages appear as the workflow advances
- completed item-level analysis can appear progressively
- when the task finishes, the final message includes:
  - a short summary
  - a preview table
  - a CSV download link

The frontend is display-only. All parsing, tool execution, analysis, and artifact generation happen in the FastAPI backend.

## Scope

This design covers one platform only: Amazon.

The system must support future platform expansion by separating:

- platform-specific product/review collection tools
- platform-agnostic LLM analysis logic
- platform-agnostic CSV export and streaming response handling

## Architecture

The implementation is split into four units.

### 1. Agent API

Responsibilities:

- serve the static frontend
- accept a user request
- parse brand and quantity from the Chinese prompt
- orchestrate tool calls
- emit SSE events during execution
- return final artifact metadata

Recommended endpoints:

- `GET /`
  - serves the SPA HTML
- `POST /api/chat`
  - accepts the raw user message
  - creates a task id and returns it
- `GET /api/chat/{task_id}/stream`
  - SSE stream for progress and result events
- `GET /api/download/{filename}`
  - serves generated CSV files

The backend should treat `POST /api/chat` as task creation and `GET /stream` as the live event channel for that task. This avoids overloading a single request with both task creation and page lifecycle concerns.

### 2. Tool Layer

Three tools are required.

#### Tool A: Amazon product collection

Use existing `scrape_amazon_products`.

Inputs:

- brand keyword
- desired count

Output:

- structured product list

#### Tool B: Amazon review summary

Use existing `summarize_reviews`.

Inputs:

- product ASIN

Output:

- review-derived structured summary including:
  - `pros`
  - `cons`
  - `overall`
  - optional raw review metadata already returned by the tool

#### Tool C: Competitor analysis

This must be separated into its own tool instead of being embedded inside the route handler.

Inputs:

- product base info
- review summary
- brand context

Output:

- structured analysis row for export

Expected fields:

- `品牌`
- `ASIN`
- `url`
- `商品标题`
- `价格`
- `评分`
- `评论数`
- `核心卖点`
- `优点评炼`
- `缺点评炼`
- `综合分析`
- `竞品定位`

This tool is intentionally platform-agnostic so later platforms can reuse the same analysis step after their own scraping/review tools are plugged in.

### 3. Artifact Layer

Responsibilities:

- collect final structured rows
- write CSV files to a local artifacts directory
- expose filename and download URL to the SSE result event

CSV is the only export format in this version.

CSV requirements:

- UTF-8 encoding
- fixed column order matching the analysis tool output
- one row per analyzed product
- file names should be unique and traceable, for example:
  - `amazon_blackview_5_20260509_153000.csv`

### 4. Static Frontend

Responsibilities:

- render the single-page interface
- collect the user message
- create a chat task through the backend
- subscribe to SSE
- append streamed messages into the message list
- show final preview table
- show CSV download link in the final assistant message

No frontend framework is required. A static HTML/CSS/JS page is sufficient and preferred for this scope.

## Execution Flow

The workflow is linear and predictable.

1. The user submits a message such as `从亚马逊获取 Blackview 5 个竞品分析`.
2. The backend parses:
   - `platform=amazon`
   - `brand=Blackview`
   - `count=5`
3. The backend emits an SSE `status` event indicating task start.
4. The backend calls `scrape_amazon_products(brand, max_valid=count)`.
5. For each returned product:
   - emit `status`
   - call `summarize_reviews(asin)`
   - call the analysis tool with product info and review summary
   - emit an `item` event for that completed product
6. After all products are processed:
   - generate CSV
   - build a preview table payload
   - emit a final `result` event
7. The frontend renders the final preview and download link in the message list.

## SSE Contract

Keep the SSE protocol intentionally small.

### `status`

Used for workflow progress text.

Example payload:

```json
{
  "type": "status",
  "message": "正在抓取 Amazon 商品..."
}
```

### `item`

Used when one product analysis is completed.

Example payload:

```json
{
  "type": "item",
  "asin": "B0XXXXXXX",
  "title": "Example Product",
  "row": {
    "品牌": "Blackview",
    "ASIN": "B0XXXXXXX",
    "url": "https://www.amazon.com/dp/B0XXXXXXX"
  }
}
```

### `result`

Used once at the end of a successful task.

Example payload:

```json
{
  "type": "result",
  "summary": "已完成 5 个竞品分析",
  "preview_columns": ["品牌", "ASIN", "url", "商品标题"],
  "preview_rows": [
    ["Blackview", "B0XXXXXXX", "https://www.amazon.com/dp/B0XXXXXXX", "Example Product"]
  ],
  "download_url": "/api/download/amazon_blackview_5_20260509_153000.csv",
  "filename": "amazon_blackview_5_20260509_153000.csv"
}
```

### `error`

Used for unrecoverable task errors or invalid user input.

Example payload:

```json
{
  "type": "error",
  "message": "请输入品牌和数量，例如：从亚马逊获取 Blackview 5 个竞品分析"
}
```

## Prompt Parsing

The first version only needs to support the narrow request family:

- `从亚马逊获取 <品牌> <数量> 个竞品分析`
- similar Chinese variants with the same intent

The parser should extract:

- platform
- brand
- quantity

If parsing fails, the backend must stop early and emit an `error` event rather than guessing.

## Error Handling

The task should degrade per item when possible.

### Input errors

- if brand or quantity cannot be extracted, emit `error`
- do not run any tools

### Product collection failure

- if `scrape_amazon_products` returns no products, emit `error`
- do not generate CSV

### Per-product review failure

- if `summarize_reviews` fails for one product, continue with the remaining products
- mark that product as partially failed
- emit a `status` event noting the degraded path

### Per-product analysis failure

- if the analysis tool fails for one product, continue with the remaining products
- produce an empty or failure-marked row only if it still adds value

### Final task failure

- only fail the whole task if zero valid product rows are produced

## CSV Schema

The output CSV columns are fixed and ordered:

1. `品牌`
2. `ASIN`
3. `url`
4. `商品标题`
5. `价格`
6. `评分`
7. `评论数`
8. `核心卖点`
9. `优点评炼`
10. `缺点评炼`
11. `综合分析`
12. `竞品定位`

The frontend preview may show all columns or a practical subset, but the downloadable file must contain the full schema.

## Local LLM Usage

Use the local endpoint:

- base URL: `http://10.0.0.21:8005`
- model: `gemma-4-31b-it-fp8`

The LLM has two distinct responsibilities:

- agent-side reasoning or structured task handling if needed by the backend flow
- competitor analysis row generation through the dedicated analysis tool

The design keeps analysis as a separate tool even if the route handler also talks to the same model endpoint.

## Files and Responsibilities

Recommended new files:

- `app.py`
  - FastAPI app, routes, static mounting, SSE endpoints
- `agent_service.py`
  - task orchestration and stream event generation
- `analysis_tools.py`
  - analysis tool for converting product + review summary into final row data
- `artifacts.py`
  - CSV writing and file metadata helpers
- `frontend/index.html`
  - SPA shell
- `frontend/app.js`
  - request submission, SSE subscription, message rendering
- `frontend/styles.css`
  - lightweight UI styling

Existing file to reuse:

- `amazon_tools.py`
  - existing Amazon scraping and review summary tools

## Testing Strategy

Required test coverage:

### Backend unit tests

- parse brand and quantity from supported Chinese prompts
- analysis tool returns the required CSV fields
- CSV writer emits the expected header order

### Backend integration-style tests

- SSE endpoint emits `status -> item -> result` in the correct order
- invalid prompts emit `error`
- zero products emits `error`
- partial per-item failures still produce final `result` when possible

### Frontend behavior tests or lightweight DOM tests

- receiving `status` appends a message
- receiving `item` appends incremental progress
- receiving `result` renders preview and download link
- receiving `error` renders error message

## Non-Goals

This version does not include:

- multi-platform routing beyond Amazon
- user authentication
- persistent chat history across browser refreshes
- multi-user concurrency guarantees
- Excel export
- advanced agent memory

## Risks

- Amazon scraping is inherently unstable and may fail intermittently
- review retrieval may be slow, so SSE must keep the UI visibly alive
- product-by-product sequential processing may feel slow for larger counts, but is acceptable for the initial version
- static frontend simplicity is a deliberate tradeoff against richer component reuse
