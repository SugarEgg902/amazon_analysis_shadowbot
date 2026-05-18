from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime

from apify_client import ApifyClient
from config.config import APIFY_API_TOKEN_2 as APIFY_API_TOKEN, APIFY_TIKTOKSHOP_ACTOR, LLM_BASE_URL, LLM_MODEL







_MAX_APIFY_RETRIES = 3


def _run_apify_search(keyword: str, max_results: int, region: str) -> list[dict]:
    client = ApifyClient(APIFY_API_TOKEN)
    run_input = {
        "scrapeType": "search",
        "searchKeywords": [keyword],
        "maxItems": max_results,
        "region": region,
        "sortBy": "relevance",
        "includeReviews": False,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": "US",
        },
    }
    print(f"[tiktokshop apify] search {keyword!r} max={max_results} region={region}")
    run = client.actor(APIFY_TIKTOKSHOP_ACTOR).call(run_input=run_input)
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


def _run_apify_reviews(product_url: str, max_reviews: int) -> list[dict]:
    client = ApifyClient(APIFY_API_TOKEN)
    run_input = {
        "scrapeType": "reviews",
        "reviewProductUrls": [product_url],
        "maxReviews": max_reviews,
        "includeReviews": True,
        "reviewsSortBy": "recommended",
        "reviewsFilterType": "all",
        "reviewsStarRating": 0,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": "US",
        },
    }
    print(f"[tiktokshop apify] reviews {product_url}")
    run = client.actor(APIFY_TIKTOKSHOP_ACTOR).call(run_input=run_input)
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


def _map_apify_item(item: dict, keyword: str) -> dict:
    product_id = str(item.get("productId", ""))
    title = (item.get("title") or "").strip()

    try:
        price_float = float(str(item.get("currentPrice", "") or "").replace(",", ""))
    except (ValueError, TypeError):
        price_float = None

    rating = item.get("rating")
    review_count = item.get("reviewCount") or 0
    sales_volume = item.get("salesVolume") or 0
    seller = (item.get("sellerName") or "").strip()
    monthly_revenue = round(price_float * sales_volume, 2) if price_float and sales_volume else ""

    is_valid = bool(product_id) and len(title) > 10 and price_float is not None and price_float > 0

    return {
        "product_id": product_id,
        "asin": product_id,
        "keyword": keyword,
        "url": item.get("productUrl", ""),
        "title": title,
        "price": f"${price_float:.2f}" if price_float else "",
        "rating": str(rating) if rating is not None else "",
        "review_count": str(review_count),
        "seller": seller,
        "monthly_sales_estimate": sales_volume,
        "monthly_revenue_estimate": monthly_revenue,
        "monthly_sales_range": "",
        "bsr_category": "",
        "bsr_rank": "",
        "bsr_display": "",
        "bullets": [],
        "is_valid": is_valid,
        "crawl_time": datetime.now().isoformat(),
    }


async def scrape_tiktokshop_products(
    keyword: str,
    max_pages: int = 2,
    max_valid: int = 5,
    headless: bool = False,
    region: str = "us",
) -> list[dict]:
    request_size = max(20, max_valid * 4)
    seen_ids: set[str] = set()
    valid: list[dict] = []

    for attempt in range(_MAX_APIFY_RETRIES):
        raw_items = await asyncio.to_thread(_run_apify_search, keyword, request_size, region)
        print(f"[tiktokshop apify] returned {len(raw_items)} raw items (attempt {attempt + 1})")
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
                print(f"[tiktokshop] {pid} ✓ {mapped['title'][:50]}")
            else:
                print(f"[tiktokshop] {item.get('productId', '')} ✗ 无效")
        if len(valid) >= max_valid:
            break
        if attempt < _MAX_APIFY_RETRIES - 1:
            request_size = min(request_size * 2, max_valid * 20)
            print(f"[tiktokshop] 有效产品不足 {max_valid}，扩大请求量至 {request_size} 重试...")

    print(f"[tiktokshop] 共 {len(valid)} 个有效产品")
    return valid


def _llm_analyze_product(product: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=LLM_BASE_URL, api_key="EMPTY")
    sys_prompt = (
        "你是一个电商竞品分析助手。"
        "根据 TikTok Shop 商品的标题、价格、评分、销量和卖家信息，用简体中文生成竞品定位分析。"
        "输出严格的 JSON，字段为 overall（一段中文分析，100-150字）。"
        "只输出 JSON，不要任何额外说明。"
    )
    user_prompt = (
        f"商品标题：{product.get('title', '')}\n"
        f"价格：{product.get('price', '')}\n"
        f"评分：{product.get('rating', '')}\n"
        f"评论数：{product.get('review_count', '')}\n"
        f"月销量：{product.get('monthly_sales_estimate', '')}\n"
        f"卖家：{product.get('seller', '')}\n"
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
    return {"pros": [], "cons": [], "overall": parsed.get("overall", "") or ""}


def _llm_summarize(positive: list[dict], negative: list[dict], product: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=LLM_BASE_URL, api_key="EMPTY")

    def fmt(reviews: list[dict]) -> str:
        if not reviews:
            return "（无）"
        lines = []
        for i, r in enumerate(reviews[:20], 1):
            lines.append(f"{i}. [{r.get('rating', '')}★] {(r.get('text') or '')[:200]}")
        return "\n".join(lines)

    sys_prompt = (
        "你是一个电商竞品分析助手。"
        "根据 TikTok Shop 商品的英文好评和差评，用简体中文总结优缺点。"
        "输出严格的 JSON，字段为 pros(string数组)、cons(string数组)、overall(一段中文总评)。"
        "每条 pros/cons 精炼成 10-25 字短句，去重，按重要性排序。"
        "只输出 JSON，不要任何额外说明。"
    )
    user_prompt = (
        f"商品：{product.get('title', '')[:100]}\n"
        f"【好评 {len(positive)} 条】\n{fmt(positive)}\n\n"
        f"【差评 {len(negative)} 条】\n{fmt(negative)}\n\n"
        "请输出 JSON。"
    )
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
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


async def scrape_tiktokshop_reviews(
    product_id: str,
    product_url: str,
    max_reviews: int = 60,
) -> dict:
    try:
        raw_reviews = await asyncio.to_thread(_run_apify_reviews, product_url, max_reviews)
    except Exception as e:
        print(f"[tiktokshop reviews] failed: {e}")
        raw_reviews = []

    if not raw_reviews:
        return {"pros": [], "cons": [], "overall": ""}

    positive = [r for r in raw_reviews if (r.get("rating") or 0) >= 4]
    negative = [r for r in raw_reviews if (r.get("rating") or 0) <= 3]
    print(f"[tiktokshop reviews] {len(positive)} pos / {len(negative)} neg")
    return await asyncio.to_thread(_llm_summarize, positive, negative, {})


