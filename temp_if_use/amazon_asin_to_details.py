import asyncio
import json
import random
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ================== 配置区 ==================
INPUT_JSON = "amazon_search_results.json"
OUTPUT_JSON = "amazon_product_details.json"

MAX_ASINS = 5                    # 目标有效产品数量
MIN_DELAY = 10.0
MAX_DELAY = 22.0


async def human_delay(min_sec=None, max_sec=None):
    await asyncio.sleep(random.uniform(min_sec or MIN_DELAY, max_sec or MAX_DELAY))


async def block_resources(route):
    """拦截非必要资源"""
    if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
        await route.abort()
    else:
        await route.continue_()


async def scrape_product(page, asin: str, original_data: dict):
    """爬取单个产品详情"""
    url = f"https://www.amazon.com/dp/{asin}"
    print(f"正在爬取: {asin}")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await human_delay(4, 8)

        # 滚动加载
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 1000)")
            await human_delay(2,4)

        data = {
            **original_data,
            "url": url,
            "crawl_time": datetime.now().isoformat(),
            "title": None,
            "price": None,
            "rating": None,
            "review_count": None,
            "bullets": [],
            "reviews": [],
            "is_valid": False,
            "invalid_reason": None
        }

        # ================== 标题 ==================
        title_selectors = [
            "#productTitle", "h1#title", "h1.a-size-large",
            "span#a-size-large", "h1[data-csa-c-type='product']", "h1"
        ]
        for selector in title_selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    title_text = await element.inner_text(timeout=8000)
                    if title_text and len(title_text.strip()) > 5:
                        data["title"] = title_text.strip()
                        break
            except:
                continue

        # 页面 title 兜底
        if not data["title"]:
            try:
                page_title = await page.title()
                data["title"] = page_title.split("|")[0].strip()
            except:
                pass

        # ================== 价格 ==================
        price_selectors = [
            ".a-price .a-offscreen",
            "span.a-price-whole",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#corePriceDisplay_desktop_feature_div .a-offscreen",
            "span.aok-offscreen",
            "[data-a-size='xl'] .a-offscreen"
        ]
        for sel in price_selectors:
            try:
                price_elem = page.locator(sel).first
                if await price_elem.count() > 0:
                    price = await price_elem.inner_text(timeout=5000)
                    if price and any(c.isdigit() for c in price):
                        data["price"] = price.strip()
                        break
            except:
                continue
        if not data["price"]:
            try:
                all_prices = await page.locator("span.a-price").all_inner_texts()
                for p in all_prices:
                    if any(c.isdigit() for c in p):
                        data["price"] = p.strip()
                        break
            except:
                pass
        # ================== 评分 ==================
# 评分
        rating_selectors = ["span.a-icon-alt", "#acrPopover span.a-icon-alt", "i.a-icon-star span"]
        for sel in rating_selectors:
            try:
                rating = await page.locator(sel).first.inner_text(timeout=5000)
                if rating and "out of" in rating.lower():
                    data["rating"] = rating.strip()
                    break
            except:
                continue

        # 评论数量
        try:
            review_count = await page.locator("#acrCustomerReviewText").first.inner_text(timeout=5000)
            data["review_count"] = review_count.strip()
        except:
            try:
                review_count = await page.locator("a[href*='customer-reviews'] span").first.inner_text(timeout=4000)
                data["review_count"] = review_count.strip()
            except:
                pass

        # ================== 五点特征 ==================
        try:
            bullets = await page.locator("#feature-bullets li span.a-list-item").all()
            for b in bullets:
                text = await b.inner_text(timeout=3000)
                if text.strip():
                    data["bullets"].append(text.strip())
        except:
            pass

        # ================== 评论（前6条） ==================
        try:
            print("    正在加载评论...")
            await page.evaluate("window.scrollBy(0, 1600)")
            await human_delay(4, 7)

            # 尝试关闭可能的遮罩层（重要！）
            await page.evaluate("""
                document.querySelectorAll('div[data-csa-c-painter="unified-trade-in-cards"]').forEach(el => el.remove());
                document.querySelectorAll('.a-modal-scroller, .modal-backdrop').forEach(el => el.remove());
            """)

            await page.evaluate("window.scrollBy(0, 800)")
            await human_delay(3, 5)

            # 不强制点击 "See all reviews"，直接抓当前可见评论
            review_cards = await page.locator("div[data-hook='review']").all()

            for card in review_cards[:10]:
                try:
                    reviewer = await card.locator("span.a-profile-name").first.inner_text(timeout=3000)
                    rating_text = await card.locator("span[data-hook='review-title']").first.inner_text(timeout=3000)
                    body = await card.locator("span[data-hook='review-body']").first.inner_text(timeout=6000)
                    
                    if body and len(body.strip()) > 15:
                        data["reviews"].append({
                            "reviewer": reviewer.strip(),
                            "rating": rating_text.strip(),
                            "text": body.strip()[:500]  # 限制长度
                        })
                except:
                    continue

        except Exception as review_err:
            print(f"    评论提取异常（已跳过）: {review_err}")

        # ================== 有效性判断（放在所有提取之后！） ==================
        title = data.get("title") or ""
        lower_title = title.lower()

        if any(err in lower_title for err in ["page not found", "sorry, we couldn't", "not available"]):
            data["invalid_reason"] = "Page Not Found"
        elif len(title) > 15 and (len(data["bullets"]) >= 2 or data.get("price") or data.get("rating")):
            data["is_valid"] = True
        else:
            data["invalid_reason"] = "缺少关键信息"

        status = "✓ 有效" if data["is_valid"] else f"✗ 无效 ({data['invalid_reason']})"
        print(f"  {status} - {title[:65] if title else '无标题'}")

        return data

    except Exception as e:
        print(f"  ✗ {asin} 失败: {e}")
        return {**original_data, "url": url, "crawl_time": datetime.now().isoformat(), 
                "is_valid": False, "invalid_reason": f"异常: {str(e)[:100]}"}


async def main():
    input_path = Path(INPUT_JSON)
    if not input_path.exists():
        print(f"错误：找不到文件 {INPUT_JSON}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    asin_map = {item["asin"]: item for item in products if item.get("asin")}
    all_asins = list(asin_map.keys())

    print(f"共发现 {len(all_asins)} 个唯一 ASIN，目标有效产品数量: {MAX_ASINS} 个")

    all_details = []
    valid_count = 0
    processed = 0
    index = 0

    async with Stealth().use_async(async_playwright()) as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.route("**/*", block_resources)

        while valid_count < MAX_ASINS and index < len(all_asins):
            asin = all_asins[index]
            original = asin_map[asin]
                
            detail = await scrape_product(page, asin, original)
            all_details.append(detail)
            processed += 1

            if detail.get("is_valid"):
                valid_count += 1
                print(f"✅ 已获得有效产品: {valid_count}/{MAX_ASINS}")
            else:
                print(f"❌ 无效，继续寻找下一个...")

            index += 1
            await human_delay()

        await browser.close()

    # 保存结果
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_details, f, ensure_ascii=False, indent=2)

    valid_products = [p for p in all_details if p.get("is_valid")]
    with open("valid_products.json", "w", encoding="utf-8") as f:
        json.dump(valid_products, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 最终完成！")
    print(f"总处理: {processed} 个 ASIN")
    print(f"有效产品: {len(valid_products)} 个（目标 {MAX_ASINS} 个）")
    print(f"全部结果 → {OUTPUT_JSON}")
    print(f"仅有效结果 → valid_products.json")


if __name__ == "__main__":
    asyncio.run(main())