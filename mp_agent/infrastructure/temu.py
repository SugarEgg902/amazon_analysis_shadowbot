from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import datetime
from typing import Any

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None


LLM_BASE_URL = "http://10.0.0.21:8000/v1"
LLM_MODEL = "qwen3.6-35b-a3b-fp8"
MIN_DELAY = 8.0
MAX_DELAY = 18.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)
_TEMU_HOME = "https://www.temu.com"


def _require_playwright_scraping() -> None:
    if async_playwright is None or Stealth is None:
        raise RuntimeError(
            "Temu scraping requires 'playwright' and 'playwright-stealth' to be installed."
        )


async def _human_delay(min_sec: float | None = None, max_sec: float | None = None) -> None:
    await asyncio.sleep(random.uniform(min_sec or MIN_DELAY, max_sec or MAX_DELAY))


async def _block_resources(route) -> None:
    if route.request.resource_type in ["media", "font"]:
        await route.abort()
    else:
        await route.continue_()


async def _new_page(playwright, headless: bool):
    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = await browser.new_context(
        viewport={"width": random.randint(1280, 1920), "height": random.randint(800, 1080)},
        user_agent=USER_AGENT,
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)
    page = await context.new_page()
    await page.route("**/*", _block_resources)
    return browser, context, page


async def _warm_up_session(page) -> None:
    """Visit Temu homepage first to establish a real session with cookies."""
    print("[temu] warming up session via homepage...")
    try:
        await page.goto(_TEMU_HOME, wait_until="domcontentloaded", timeout=60000)
        await _human_delay(5, 10)
        await page.evaluate("window.scrollBy(0, 400)")
        await _human_delay(2, 4)
        await page.evaluate("window.scrollBy(0, 300)")
        await _human_delay(2, 3)
    except Exception as e:
        print(f"[temu] warm-up warning: {e}")


def _parse_price_amount(price_text: str | None) -> float | None:
    match = re.search(r"(\d[\d,]*\.?\d*)", str(price_text or ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _llm_summarize(positive: list[dict], negative: list[dict]) -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=LLM_BASE_URL, api_key="EMPTY")

    def fmt(reviews: list[dict]) -> str:
        if not reviews:
            return "（无）"
        lines = []
        for i, r in enumerate(reviews, 1):
            lines.append(f"{i}. [{r.get('rating','')}] {r.get('title','')}\n   {r.get('text','')}")
        return "\n".join(lines)

    sys_prompt = (
        "你是一个电商商品评论分析助手。"
        "你将收到若干条来自 Temu 的评论（好评和差评），"
        "请用简体中文总结产品的优点和缺点。"
        "输出严格的 JSON，字段为 pros(string数组)、cons(string数组)、overall(一段中文总评)。"
        "每条 pros/cons 请精炼成 10-25 字短句，去重，按重要性排序。"
        "只输出 JSON，不要任何额外说明。"
    )
    user_prompt = (
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


async def _scrape_search_page(page, keyword: str, page_num: int) -> list[dict]:
    url = (
        f"https://www.temu.com/search_result.html"
        f"?search_key={keyword.replace(' ', '+')}&search_method=recent&page={page_num}"
    )
    print(f"[temu search] {keyword} page={page_num}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await _human_delay(5, 10)

        title = await page.title()
        if "verify" in title.lower() or "captcha" in title.lower():
            print("[temu search] bot check detected, waiting...")
            await _human_delay(10, 20)

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await _human_delay(1, 3)

        # Temu product links contain "-g-{goods_id}.html"
        links = await page.locator('a[href*="-g-"]').all()
        out: list[dict] = []
        seen: set[str] = set()
        for link in links:
            try:
                href = await link.get_attribute("href") or ""
                m = re.search(r"-g-(\d{12,})", href)
                if m:
                    goods_id = m.group(1)
                    if goods_id not in seen:
                        seen.add(goods_id)
                        # Build canonical product URL
                        if href.startswith("http"):
                            product_url = href.split("?")[0]
                        else:
                            product_url = _TEMU_HOME + href.split("?")[0]
                        out.append({
                            "goods_id": goods_id,
                            "keyword": keyword,
                            "page": page_num,
                            "url": product_url,
                            "timestamp": datetime.now().isoformat(),
                        })
            except Exception:
                continue
        print(f"[temu search] got {len(out)} goods IDs")
        return out
    except Exception as e:
        print(f"[temu search] failed: {e}")
        return []


async def _scrape_item_detail(page, goods_id: str, original: dict) -> dict:
    url = original.get("url") or f"https://www.temu.com/goods.html?goods_id={goods_id}"
    print(f"[temu detail] {goods_id}")
    data: dict[str, Any] = {
        **original,
        "goods_id": goods_id,
        "url": url,
        "crawl_time": datetime.now().isoformat(),
        "title": None,
        "price": None,
        "rating": None,
        "review_count": None,
        "sold_count": None,
        "monthly_sales_estimate": "",
        "monthly_revenue_estimate": "",
        "monthly_sales_range": "",
        "bsr_rank": "",
        "bsr_category": "",
        "bsr_display": "",
        "bullets": [],
        "is_valid": False,
        "invalid_reason": None,
    }
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await _human_delay(5, 10)
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 800)")
            await _human_delay(2, 4)

        # Try extracting from embedded JSON first (window.__NEXT_DATA__ or similar)
        body_html = await page.evaluate("document.body.innerHTML")

        # title
        for sel in ["h1", "[class*='title']", "[class*='goods-title']", "[class*='product-title']"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    text = await el.inner_text(timeout=8000)
                    if text and len(text.strip()) > 5:
                        data["title"] = text.strip()
                        break
            except Exception:
                continue

        # price — try JSON blob first
        price_m = re.search(r'"price"\s*:\s*"?\$?([\d.]+)"?', body_html)
        if price_m:
            data["price"] = f"${price_m.group(1)}"
        else:
            for sel in [
                "[class*='price']",
                "[class*='Price']",
                "[data-testid*='price']",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        p = await el.inner_text(timeout=5000)
                        if p and any(c.isdigit() for c in p):
                            data["price"] = p.strip()
                            break
                except Exception:
                    continue

        # rating — try JSON blob
        rating_m = re.search(
            r'"(?:star|rating|score)"\s*:\s*"?([\d.]+)"?', body_html
        )
        if rating_m:
            data["rating"] = rating_m.group(1)
        else:
            try:
                body_text = await page.locator("body").inner_text(timeout=5000)
                rm = re.search(r"([\d.]+)\s*(?:out of 5|/5|stars?|分)", body_text, re.IGNORECASE)
                if rm:
                    data["rating"] = rm.group(1)
            except Exception:
                pass

        # sold_count — try JSON "sales_tip" or text pattern
        sold_int = None
        sales_m = re.search(
            r'"sales_tip"\s*:\s*"([^"]*)"', body_html
        )
        if sales_m:
            tip = sales_m.group(1)
            nm = re.search(r"([\d,]+)", tip)
            if nm:
                sold_int = int(nm.group(1).replace(",", ""))
                data["sold_count"] = tip
        if sold_int is None:
            try:
                body_text = await page.locator("body").inner_text(timeout=5000)
                sm = re.search(
                    r"([\d,]+)\+?\s*(?:sold|已售|件已售|orders?)", body_text, re.IGNORECASE
                )
                if sm:
                    sold_int = int(sm.group(1).replace(",", ""))
                    data["sold_count"] = sm.group(0).strip()
            except Exception:
                pass

        # review_count
        review_m = re.search(r'"review_count"\s*:\s*(\d+)', body_html)
        if review_m:
            data["review_count"] = int(review_m.group(1))
        else:
            try:
                body_text = await page.locator("body").inner_text(timeout=5000)
                rcm = re.search(
                    r"([\d,]+)\s*(?:reviews?|ratings?|评价|评论)", body_text, re.IGNORECASE
                )
                if rcm:
                    data["review_count"] = rcm.group(1)
            except Exception:
                pass

        # bullets from product description / spec list
        for sel in [
            "[class*='description'] li",
            "[class*='spec'] li",
            "[class*='detail'] li",
            "[class*='feature'] li",
        ]:
            try:
                items = await page.locator(sel).all()
                if items:
                    for item in items[:10]:
                        t = await item.inner_text(timeout=3000)
                        if t.strip():
                            data["bullets"].append(t.strip())
                    if data["bullets"]:
                        break
            except Exception:
                continue

        # monthly estimates
        if sold_int is not None:
            data["monthly_sales_estimate"] = sold_int
            price_float = _parse_price_amount(data.get("price"))
            if price_float is not None:
                data["monthly_revenue_estimate"] = round(price_float * sold_int, 2)

        title = data.get("title") or ""
        if len(title) > 10 and data.get("price"):
            data["is_valid"] = True
        else:
            data["invalid_reason"] = "缺少关键信息"

        status = "✓ 有效" if data["is_valid"] else f"✗ 无效({data['invalid_reason']})"
        print(f"  {status} - {(title[:60] if title else '无标题')}")
        return data

    except Exception as e:
        data["invalid_reason"] = f"异常: {str(e)[:100]}"
        print(f"  ✗ 异常: {e}")
        return data


async def scrape_temu_products(
    keyword: str,
    max_pages: int = 2,
    max_valid: int = 5,
    headless: bool = False,
) -> list[dict]:
    """搜索关键词 -> 收集 goods_id -> 抓详情 -> 返回有效产品列表。"""
    _require_playwright_scraping()

    all_items: list[dict] = []
    seen: set[str] = set()
    valid: list[dict] = []

    async with Stealth().use_async(async_playwright()) as pw:
        browser, _ctx, page = await _new_page(pw, headless)
        try:
            await _warm_up_session(page)
            for pn in range(1, max_pages + 1):
                items = await _scrape_search_page(page, keyword, pn)
                for it in items:
                    if it["goods_id"] not in seen:
                        seen.add(it["goods_id"])
                        all_items.append(it)
                await _human_delay()

            print(f"[temu] 共 {len(all_items)} 个唯一 goods_id, 目标有效 {max_valid}")

            for original in all_items:
                if len(valid) >= max_valid:
                    break
                detail = await _scrape_item_detail(page, original["goods_id"], original)
                if detail.get("is_valid"):
                    valid.append(detail)
                    print(f"[temu] 已拿到 {len(valid)}/{max_valid} 个有效产品")
                await _human_delay()
        finally:
            await browser.close()

    return valid


async def scrape_temu_reviews(goods_id: str, product_url: str, max_reviews: int = 60) -> dict:
    """从 Temu 商品详情页抓取买家评论并用 LLM 总结优缺点。"""
    _require_playwright_scraping()

    reviews: list[dict] = []

    async with Stealth().use_async(async_playwright()) as pw:
        browser, _ctx, page = await _new_page(pw, headless=True)
        try:
            await _warm_up_session(page)
            url = product_url or f"https://www.temu.com/goods.html?goods_id={goods_id}"
            print(f"[temu reviews] loading {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await _human_delay(5, 8)
            # Scroll to load review section
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 800)")
                await _human_delay(1, 2)

            # Try multiple review card selectors
            review_selectors = [
                "[class*='review-item']",
                "[class*='ReviewItem']",
                "[class*='comment-item']",
                "[class*='CommentItem']",
                "[class*='review-card']",
            ]
            cards = []
            for sel in review_selectors:
                try:
                    found = await page.locator(sel).all()
                    if found:
                        cards = found
                        print(f"[temu reviews] found {len(cards)} review cards via {sel}")
                        break
                except Exception:
                    continue

            for card in cards[:max_reviews]:
                try:
                    review: dict[str, Any] = {}

                    # Rating from aria-label or star count
                    try:
                        card_html = await card.inner_html(timeout=3000)
                        rm = re.search(r"([\d.]+)\s*(?:out of 5|/5|stars?)", card_html, re.IGNORECASE)
                        if rm:
                            review["rating"] = float(rm.group(1))
                        else:
                            # Count filled star elements
                            filled = await card.locator("[class*='star'][class*='fill'], [class*='star-fill'], [class*='filled']").count()
                            if filled > 0:
                                review["rating"] = float(filled)
                    except Exception:
                        pass

                    # Review text
                    for text_sel in [
                        "[class*='review-content']",
                        "[class*='ReviewContent']",
                        "[class*='comment-content']",
                        "[class*='CommentContent']",
                        "[class*='review-text']",
                        "p",
                    ]:
                        try:
                            el = card.locator(text_sel).first
                            if await el.count() > 0:
                                text = await el.inner_text(timeout=3000)
                                if text and len(text.strip()) > 5:
                                    review["text"] = text.strip()
                                    break
                        except Exception:
                            continue

                    if review.get("text"):
                        reviews.append(review)
                except Exception:
                    continue
        finally:
            await browser.close()

    positive = [r for r in reviews if r.get("rating", 0) >= 4]
    negative = [r for r in reviews if r.get("rating", 5) <= 2]

    print(f"[temu reviews] {len(positive)} positive / {len(negative)} negative")

    if positive or negative:
        print(f"[temu llm] summarizing {len(positive)} pos / {len(negative)} neg ...")
        summary = _llm_summarize(positive, negative)
    else:
        summary = {"pros": [], "cons": [], "overall": ""}

    return {
        "goods_id": goods_id,
        "review_count": len(reviews),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "pros": summary["pros"],
        "cons": summary["cons"],
        "overall": summary["overall"],
    }

