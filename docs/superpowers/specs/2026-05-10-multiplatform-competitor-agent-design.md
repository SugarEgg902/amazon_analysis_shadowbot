# Multi-Platform Competitor Agent Design

## Goal

Upgrade the current Amazon-only single-turn workflow into a multi-turn chat agent for e-commerce competitor analysis.

Version 1 must:

- support multi-turn conversations
- keep session state in memory only
- ask follow-up questions when required parameters are missing
- use a primary LLM agent to understand the user request and decide which platform workflow tool to call
- keep Amazon as the only implemented platform for now
- preserve structured result rendering for progress, preview data, and CSV download artifacts

The primary agent uses the DashScope OpenAI-compatible API:

- `base_url`: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `model`: `glm-4.6`
- `api_key`: `DASHSCOPE_API_KEY`

## Non-Goals

This design explicitly does not cover:

- persistent sessions across restarts or page refreshes
- non-e-commerce analysis tools
- a fully generic tool marketplace
- implementing a second platform in version 1
- replacing the existing Amazon scraping and review-summary internals

## User Experience

The product behaves like a chat agent instead of a one-shot parser.

Examples:

- `帮我看一下 Blackview 的竞品`
- `先看 Amazon 上的`
- `数量 5 个`

Expected behavior:

1. The user can provide the request across multiple turns.
2. The agent extracts or remembers platform, brand, and count across turns.
3. If a required field is missing, the agent asks a focused follow-up question instead of failing.
4. Once the required fields are complete, the agent calls the platform workflow tool.
5. The user sees assistant messages plus structured progress and result blocks in the same conversation stream.

Required fields for version 1:

- `platform`
- `brand`
- `count`

Version 1 defaults:

- no silent default platform selection
- no silent default count selection
- ask for missing required fields instead of guessing

## Scope

Version 1 supports one implemented workflow:

- Amazon competitor analysis

The architecture must make the next platform addition primarily a matter of:

- adding a new platform workflow
- registering it in the workflow registry
- exposing its schema to the primary agent

The primary agent should not need platform-specific orchestration logic embedded in prompts or route handlers.

## Architecture

The system is split into six units.

### 1. Session API Layer

Responsibilities:

- create and manage chat sessions
- accept user messages for a session
- create per-message runs
- expose SSE streams for run output
- serve artifact downloads

Recommended endpoints:

- `POST /api/sessions`
  - create a new in-memory session
  - return `session_id`
- `GET /api/sessions/{session_id}`
  - return current session metadata, known slots, and message history
- `POST /api/sessions/{session_id}/messages`
  - accept one user message
  - create a `run_id`
  - start background execution
  - return `session_id` and `run_id`
- `GET /api/sessions/{session_id}/runs/{run_id}/stream`
  - stream assistant and tool events for that run
- `GET /api/download/{filename}`
  - return generated CSV files

### 2. Session Store

Responsibilities:

- store session state in memory
- retain conversation history for the active browser lifetime
- retain extracted slot values across turns
- track active runs and prevent conflicting concurrent execution

Recommended session shape:

```python
Session:
  session_id: str
  messages: list[Message]
  slots:
    platform: str | None
    brand: str | None
    count: int | None
  active_run_id: str | None
```

Version 1 rule:

- allow only one active run per session

If the frontend sends another message while a run is active, the backend should reject it with a clear error or require the frontend to wait until completion.

### 3. Primary Agent Layer

Responsibilities:

- read the session history and current slot state
- decide whether the user is clarifying a previous request or starting a new task
- ask follow-up questions when required fields are missing
- choose and call the correct high-level workflow tool when parameters are complete
- produce the final assistant response after tool execution

The primary agent does not directly call low-level Amazon functions.

It should operate on:

- conversation messages
- current known slots
- workflow tool schemas

It should produce one of two outcomes:

1. assistant reply only
2. tool call followed by assistant reply

### 4. Workflow Registry

Responsibilities:

- register platform-specific competitor-analysis workflows
- provide tool schema definitions to the primary agent
- map tool calls from the agent to concrete Python callables

Version 1 registry contents:

- `run_amazon_competitor_analysis(brand, count)`

Future examples:

- `run_temu_competitor_analysis(brand, count)`
- `run_tiktok_shop_competitor_analysis(brand, count)`

This registry is the main platform extension point.

### 5. Platform Workflow Layer

Responsibilities:

- implement one complete competitor-analysis workflow per platform
- emit progress events during long-running execution
- call platform-specific collection tools and shared analysis/export helpers
- return structured result data back to the primary agent

Amazon workflow in version 1:

1. scrape products with `scrape_amazon_products`
2. summarize reviews with `summarize_reviews`
3. build analysis rows with `build_analysis_row`
4. write CSV with `write_analysis_csv`
5. return preview rows, artifact metadata, and a concise execution summary

The workflow layer owns iteration, retries, partial failure handling, and result shaping.
The primary agent should not manage per-product loops itself.

### 6. Shared Analysis and Artifact Layer

Responsibilities:

- keep `build_analysis_row` platform-agnostic where possible
- keep CSV generation and artifact metadata independent of platform
- support reuse by future platform workflows

This layer remains below the workflow boundary and is not exposed directly to the primary agent.

## Agent Operating Model

The core rule is:

- the LLM interprets the user request first
- the LLM decides whether it has enough information
- the LLM decides whether to ask a follow-up question or call a workflow tool

This replaces the current regex-first entry path.

### Slot Collection

Version 1 tracks three slots:

- `platform`
- `brand`
- `count`

Behavior rules:

- if `platform` is missing, ask for the platform
- if `brand` is missing, ask for the brand or keyword
- if `count` is missing, ask for the number of products
- if all three are present and `platform` is supported, call the workflow tool
- if the requested platform is unsupported, the assistant should say so explicitly instead of forcing Amazon

### Session Memory Rules

- Slot values persist inside the session until replaced or the session ends.
- A later user message can update one slot without re-entering the others.
- The primary agent should prefer the latest explicit user instruction if there is a conflict.

Example:

1. User: `帮我看一下 Blackview 的竞品`
2. Agent: `你想看哪个平台？`
3. User: `Amazon`
4. Agent: `要分析几个商品？`
5. User: `5 个`
6. Agent: calls `run_amazon_competitor_analysis`

## Tool Surface

The primary agent sees only high-level tools.

Version 1 tool schema:

### `run_amazon_competitor_analysis`

Inputs:

- `brand`: string
- `count`: integer

Output:

- `platform`
- `brand`
- `count`
- `rows`
- `preview_columns`
- `preview_rows`
- `filename`
- `download_url`
- `summary`

Internal tool composition for Amazon remains hidden behind this workflow boundary.

## Execution Flow

For each user message:

1. Load the session.
2. Append the new user message to session history.
3. Build the agent context from:
   - conversation history
   - current slot state
   - supported workflow tools
4. Call the primary LLM agent.
5. If the agent responds with a follow-up question:
   - append the assistant message to history
   - emit an `assistant` event
   - end the run
6. If the agent emits a workflow tool call:
   - mark the run active
   - execute the workflow
   - emit structured progress events during execution
   - feed the workflow result back to the primary agent
   - have the primary agent produce the final assistant summary
   - append result messages to history
   - end the run

## SSE Contract

Version 1 uses a mixed event model: assistant conversation plus structured machine-readable blocks.

Recommended event types:

### `assistant`

Used for natural-language assistant messages, including follow-up questions and final summaries.

Example:

```json
{
  "type": "assistant",
  "message": "你想分析哪个平台？目前我支持 Amazon。"
}
```

### `tool_status`

Used for workflow progress updates.

Example:

```json
{
  "type": "tool_status",
  "tool": "run_amazon_competitor_analysis",
  "message": "正在抓取 Amazon 商品..."
}
```

### `artifact`

Used for structured result blocks such as preview tables and downloadable files.

Example:

```json
{
  "type": "artifact",
  "artifact_type": "csv_preview",
  "summary": "已完成 5 个竞品分析",
  "preview_columns": ["品牌", "ASIN", "url"],
  "preview_rows": [["Blackview", "B0TEST", "https://www.amazon.com/dp/B0TEST"]],
  "filename": "amazon_blackview_5_20260510_120000.csv",
  "download_url": "/api/download/amazon_blackview_5_20260510_120000.csv"
}
```

### `error`

Used for user-visible failures.

Example:

```json
{
  "type": "error",
  "message": "Amazon 工作流执行失败: 没有抓取到有效商品"
}
```

### `done`

Used to mark the end of a run.

Example:

```json
{
  "type": "done"
}
```

## Error Handling

Errors should be handled at the appropriate layer.

Primary agent layer:

- unsupported platform
- missing required parameters
- malformed tool arguments

Workflow layer:

- platform scraping failure
- review summary failure
- per-item analysis failure
- CSV generation failure

Behavior requirements:

- a missing parameter should trigger a follow-up question, not an error
- an unsupported platform should return a normal assistant response, not a crash
- per-item failures should degrade gracefully when possible
- terminal workflow failure should emit `error` and end the run cleanly

## Frontend Impact

The frontend remains lightweight.

It must:

- create a session on load
- keep the active `session_id`
- submit messages against that session
- open the run stream for each submitted message
- render assistant messages in the chat log
- render structured status and artifact blocks inline

The frontend does not parse intent or orchestrate tools.

## Implementation Boundaries for Version 1

Required:

- replace regex-first orchestration with primary-agent-first orchestration
- add session and run concepts
- add follow-up question behavior
- add workflow registry abstraction
- wrap the existing Amazon pipeline as a high-level workflow tool
- switch the primary agent to DashScope `glm-4.6`

Deferred:

- second platform implementation
- persistent storage
- multi-user auth
- cancellation and resume
- concurrent runs inside one session

## Testing Strategy

The implementation should be verified with tests at four levels.

1. Session store tests
   - create session
   - update slots across multiple turns
   - reject concurrent active runs

2. Primary agent orchestration tests
   - asks follow-up question when `platform` is missing
   - asks follow-up question when `count` is missing
   - calls Amazon workflow when all parameters are complete
   - rejects unsupported platform cleanly

3. Workflow registry and Amazon workflow tests
   - registry resolves the right workflow
   - Amazon workflow returns progress and final artifact payload
   - partial failures degrade correctly

4. API and SSE tests
   - session creation works
   - message submission returns `run_id`
   - SSE emits `assistant`, `tool_status`, `artifact`, `error`, and `done` as expected

## Migration Notes

The current `parse_competitor_request()` path should be removed from the main entry flow after the agent-based path is in place.

If backward compatibility is temporarily needed during the transition, it may remain as an internal fallback for tests or guarded rollout, but it should no longer define the product behavior.
