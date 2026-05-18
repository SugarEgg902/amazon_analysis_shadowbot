from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from urllib.parse import quote_plus

from apify_client import ApifyClient
from config.config import APIFY_API_TOKEN_2 as APIFY_API_TOKEN, APIFY_CDISCOUNT_ACTOR, LLM_BASE_URL, LLM_MODEL, EUR_TO_USD









_MAX_APIFY_RETRIES = 3


def _build_start_url(keyword: str) -> str:
    slug = quote_plus(keyword.lower().replace(" ", "-"))
    return f"https://www.cdiscount.com/search/10/{slug}.html"


def _run_apify(keyword: str, max_results: int, max_pages: int) -> list[dict]:
    client = ApifyClient(APIFY_API_TOKEN)
    run_input = {
        "startUrl": _build_start_url(keyword),
        "keyword": keyword,
        "results_wanted": max_results,
        "max_pages": max_pages,
        "includeSponsored": True,
        "proxyConfiguration": {"useApifyProxy": False},
    }
    print(f"[cdiscount apify] search {keyword!r} max={max_results} pages={max_pages}")
    run = client.actor(APIFY_CDISCOUNT_ACTOR).call(run_input=run_input)
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


def _format_bullets(bullet_points: list[dict]) -> list[str]:
    result = []
    for bp in bullet_points or []:
        label = (bp.get("label") or "").strip()
        value = (bp.get("value") or "").strip()
        if label and value:
            result.append(f"{label}: {value}")
        elif label:
            result.append(label)
    return result


def _map_apify_item(item: dict, keyword: str) -> dict:
    product_id = str(item.get("productId", ""))
    title = (item.get("productName") or "").strip()

    price_eur = item.get("price")
    try:
        price_eur_float = float(price_eur)
    except (TypeError, ValueError):
        price_eur_float = None

    striked_eur = item.get("strikedPrice")
    try:
        striked_eur_float = float(striked_eur)
    except (TypeError, ValueError):
        striked_eur_float = None

    price_usd = round(price_eur_float * EUR_TO_USD, 2) if price_eur_float else None
    bullets = _format_bullets(item.get("bulletPoints", []))

    # derive top-level category from categoryCodePath e.g. "07/0703/..." -> "07"
    category_path = item.get("categoryCodePath", "")
    top_category = category_path.split("/")[0] if category_path else ""

    is_valid = bool(product_id) and len(title) > 10 and price_eur_float is not None and price_eur_float > 0

    return {
        "product_id": product_id,
        "asin": product_id,
        "keyword": keyword,
        "url": item.get("productUrl", ""),
        "title": title,
        "price": f"€{price_eur_float:.2f}" if price_eur_float else "",
        "price_eur": price_eur_float,
        "price_usd": price_usd,
        "striked_price": f"€{striked_eur_float:.2f}" if striked_eur_float else "",
        "seller": (item.get("sellerName") or "").strip(),
        "bullets": bullets,
        "bsr_category": top_category,
        "monthly_sales_estimate": "",
        "monthly_revenue_estimate": "",
        "monthly_sales_range": "",
        "bsr_rank": "",
        "bsr_display": "",
        "rating": "",
        "review_count": "",
        "is_valid": is_valid,
        "crawl_time": datetime.now().isoformat(),
    }


async def scrape_cdiscount_products(
    keyword: str,
    max_pages: int = 3,
    max_valid: int = 5,
    headless: bool = False,
) -> list[dict]:
    request_size = max(20, max_valid * 4)
    seen_ids: set[str] = set()
    valid: list[dict] = []

    for attempt in range(_MAX_APIFY_RETRIES):
        raw_items = await asyncio.to_thread(_run_apify, keyword, request_size, max_pages)
        print(f"[cdiscount apify] returned {len(raw_items)} raw items (attempt {attempt + 1})")
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
                print(f"[cdiscount] {pid} ✓ {mapped['title'][:50]}")
            else:
                print(f"[cdiscount] {pid or item.get('productId', '')} ✗ 无效")
        if len(valid) >= max_valid:
            break
        if attempt < _MAX_APIFY_RETRIES - 1:
            request_size = min(request_size * 2, max_valid * 20)
            print(f"[cdiscount] 有效产品不足 {max_valid}，扩大请求量至 {request_size} 重试...")

    print(f"[cdiscount] 共 {len(valid)} 个有效产品")
    return valid


def _llm_analyze_product(product: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=LLM_BASE_URL, api_key="EMPTY")
    bullets_str = "；".join(product.get("bullets", [])[:6]) or "（无）"

    sys_prompt = (
        "你是一个电商竞品分析助手。"
        "根据 Cdiscount 商品的标题、价格、卖家和法语规格参数，用简体中文生成竞品定位分析。"
        "输出严格的 JSON，字段为 pros(string数组，从规格中提炼优点)、"
        "cons(string数组，潜在缺点或不确定项)、overall（一段中文分析，100-150字）。"
        "每条 pros/cons 精炼成 10-25 字短句。只输出 JSON，不要任何额外说明。"
    )
    user_prompt = (
        f"商品标题：{product.get('title', '')}\n"
        f"价格：{product.get('price', '')}（原价 {product.get('striked_price', '')}）\n"
        f"卖家：{product.get('seller', '')}\n"
        f"规格参数（法语）：{bullets_str}\n"
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
        parsed = {"pros": [], "cons": [], "overall": raw}
    return {
        "pros": parsed.get("pros", []) or [],
        "cons": parsed.get("cons", []) or [],
        "overall": parsed.get("overall", "") or "",
    }


async def scrape_cdiscount_reviews(
    product_id: str,
    product_url: str,
    max_reviews: int = 60,
) -> dict:
    return {"pros": [], "cons": [], "overall": ""}
