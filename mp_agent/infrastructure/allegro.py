from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime

from apify_client import ApifyClient
from config.config import APIFY_API_TOKEN, APIFY_ALLEGRO_ACTOR, LLM_BASE_URL, LLM_MODEL, PLN_TO_USD









_MAX_APIFY_RETRIES = 3


def _run_apify(keyword: str, max_results: int) -> list[dict]:
    client = ApifyClient(APIFY_API_TOKEN)
    run_input = {
        "searchQueries": [keyword],
        "startUrls": [],
        "maxItemsPerQuery": max_results,
        "condition": "all",
        "sortBy": "relevance",
    }
    print(f"[allegro apify] running actor for {keyword!r} max={max_results}")
    run = client.actor(APIFY_ALLEGRO_ACTOR).call(run_input=run_input)
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


def _map_apify_item(item: dict, keyword: str) -> dict:
    product_id = str(item.get("id", ""))
    title = (item.get("title") or "").strip()
    price_pln = item.get("price")
    price_usd = round(price_pln * PLN_TO_USD, 2) if price_pln else None
    rating = item.get("rating")
    review_count = item.get("reviewCount") or 0
    category = item.get("category") or ""
    top_category = category.split(">")[0].strip() if ">" in category else category

    is_valid = (
        bool(re.match(r"^\d+$", product_id))
        and len(title) > 10
        and price_usd is not None
        and price_usd > 0
    )

    return {
        "product_id": product_id,
        "asin": product_id,
        "keyword": keyword,
        "url": item.get("url", f"https://allegro.pl/oferta/{product_id}"),
        "title": title,
        "price_pln": price_pln,
        "price": f"${price_usd:.2f}" if price_usd else "",
        "rating": str(rating) if rating is not None else "",
        "review_count": review_count,
        "condition": item.get("condition", ""),
        "seller": item.get("seller", ""),
        "seller_rating": item.get("sellerRating"),
        "category": category,
        "bsr_category": top_category,
        "parameters": item.get("parameters") or {},
        "bullets": [],
        "description": "",
        "monthly_sales_estimate": "",
        "monthly_revenue_estimate": "",
        "monthly_sales_range": "",
        "bsr_rank": "",
        "bsr_display": "",
        "总销量估算": "",
        "总销售额估算": "",
        "is_valid": is_valid,
        "crawl_time": datetime.now().isoformat(),
    }


async def scrape_allegro_products(
    keyword: str,
    max_pages: int = 2,
    max_valid: int = 5,
    headless: bool = False,
) -> list[dict]:
    request_size = max(20, max_valid * 4)
    seen_ids: set[str] = set()
    valid: list[dict] = []

    for attempt in range(_MAX_APIFY_RETRIES):
        raw_items = await asyncio.to_thread(_run_apify, keyword, request_size)
        print(f"[allegro apify] returned {len(raw_items)} raw items (attempt {attempt + 1})")
        for item in raw_items:
            if len(valid) >= max_valid:
                break
            mapped = _map_apify_item(item, keyword)
            pid = mapped["product_id"]
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            if mapped["is_valid"]:
                valid.append(mapped)
                print(f"[allegro] {pid} ✓ {mapped['title'][:50]}")
            else:
                print(f"[allegro] {item.get('id', '')} ✗ 无效")
        if len(valid) >= max_valid:
            break
        if attempt < _MAX_APIFY_RETRIES - 1:
            request_size = min(request_size * 2, max_valid * 20)
            print(f"[allegro] 有效产品不足 {max_valid}，扩大请求量至 {request_size} 重试...")

    print(f"[allegro] 共 {len(valid)} 个有效产品")
    return valid


def _llm_analyze_product(product: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=LLM_BASE_URL, api_key="EMPTY")
    params = product.get("parameters") or {}
    params_str = "；".join(f"{k}: {v}" for k, v in list(params.items())[:8])

    sys_prompt = (
        "你是一个电商竞品分析助手。"
        "根据商品的标题、价格、评分、评论数和规格参数，用简体中文生成竞品定位分析。"
        "输出严格的 JSON，字段为 overall（一段中文分析，100-150字）。"
        "只输出 JSON，不要任何额外说明。"
    )
    user_prompt = (
        f"商品标题：{product.get('title', '')}\n"
        f"价格：{product.get('price', '')}（原价 {product.get('price_pln', '')} PLN）\n"
        f"评分：{product.get('rating', '')}\n"
        f"评论数：{product.get('review_count', '')}\n"
        f"商品状态：{product.get('condition', '')}\n"
        f"卖家：{product.get('seller', '')}（好评率 {product.get('seller_rating', '')}%）\n"
        f"规格参数：{params_str}\n"
        "请输出 JSON。"
    )
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"overall": raw}
    return {
        "pros": [],
        "cons": [],
        "overall": parsed.get("overall", "") or "",
    }


async def scrape_allegro_reviews(
    product_id: str,
    product_url: str,
    max_reviews: int = 60,
) -> dict:
    return {"pros": [], "cons": [], "overall": ""}
