from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from amazon_tools import scrape_amazon_products, summarize_reviews
from analysis_tools import build_analysis_row
from artifacts import CSV_COLUMNS, write_analysis_csv

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

    match = re.fullmatch(r"从亚马逊获取\s*(.+?)\s+(\d+)\s*个竞品分析", text)
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
    task = AgentTask(
        task_id=uuid.uuid4().hex,
        message=message,
        queue=asyncio.Queue(),
    )
    TASKS[task.task_id] = task
    return task


async def emit_event(queue: asyncio.Queue, payload: dict) -> None:
    await queue.put(payload)


def _build_download_url(path: Path) -> str:
    return f"/api/download/{path.name}"


async def run_task(message: str, queue: asyncio.Queue) -> None:
    parsed = parse_competitor_request(message)
    if parsed is None:
        await emit_event(
            queue,
            {
                "type": "error",
                "message": "请输入品牌和数量，例如：从亚马逊获取 Blackview 5 个竞品分析",
            },
        )
        return

    brand = parsed["brand"]
    count = parsed["count"]

    await emit_event(queue, {"type": "status", "message": "正在抓取 Amazon 商品..."})
    try:
        products = await scrape_amazon_products(brand, max_valid=count)
    except Exception as exc:
        await emit_event(queue, {"type": "error", "message": f"抓取商品失败: {exc}"})
        return

    if not products:
        await emit_event(queue, {"type": "error", "message": "没有抓取到有效商品"})
        return

    rows: list[dict] = []
    for product in products:
        asin = product.get("asin", "")
        await emit_event(queue, {"type": "status", "message": f"正在分析 {asin} ..."})

        review_summary: dict
        try:
            review_summary = await summarize_reviews(asin)
        except Exception as exc:
            await emit_event(queue, {"type": "status", "message": f"{asin} 评论摘要失败: {exc}"})
            review_summary = {"pros": [], "cons": [], "overall": ""}

        try:
            row = await asyncio.to_thread(
                build_analysis_row,
                brand=brand,
                product=product,
                review_summary=review_summary,
            )
        except Exception as exc:
            await emit_event(queue, {"type": "status", "message": f"{asin} 分析生成失败: {exc}"})
            continue

        rows.append(row)
        await emit_event(
            queue,
            {
                "type": "item",
                "asin": asin,
                "title": product.get("title", ""),
                "row": row,
            },
        )

    if not rows:
        await emit_event(queue, {"type": "error", "message": "没有生成有效竞品分析结果"})
        return

    try:
        csv_path = write_analysis_csv(rows, brand=brand, count=count)
    except Exception as exc:
        await emit_event(queue, {"type": "error", "message": f"写入 CSV 失败: {exc}"})
        return

    await emit_event(
        queue,
        {
            "type": "result",
            "summary": f"已完成 {len(rows)} 个竞品分析",
            "preview_columns": CSV_COLUMNS,
            "preview_rows": [[row.get(column, "") for column in CSV_COLUMNS] for row in rows],
            "download_url": _build_download_url(csv_path),
            "filename": csv_path.name,
        },
    )
