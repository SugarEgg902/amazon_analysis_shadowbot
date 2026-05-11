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
