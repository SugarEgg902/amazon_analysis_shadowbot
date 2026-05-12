import asyncio
import random
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # 推荐的 stealth 使用方式


# ================== 配置区 ==================
KEYWORDS = [
    "doogee",
    "ulefone",
    # 在这里添加你的搜索关键词
]

MAX_PAGES_PER_KEYWORD = 2          # 每关键词最多爬几页（建议 2-3）
OUTPUT_FILE = "amazon_search_results.json"

# 控制速度（无代理时必须慢）
MIN_DELAY = 8.0
MAX_DELAY = 18.0


async def human_delay(min_sec=None, max_sec=None):
    """随机人类延迟"""
    delay = random.uniform(min_sec or MIN_DELAY, max_sec or MAX_DELAY)
    await asyncio.sleep(delay)


async def block_resources(route):
    """拦截非必要资源，加快加载并降低指纹"""
    if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
        await route.abort()
    else:
        await route.continue_()


async def scrape_search_page(page, keyword: str, page_num: int):
    """爬取单页搜索结果"""
    url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}&page={page_num}"
    
    print(f"正在访问: {keyword} - 第 {page_num} 页")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await human_delay(3, 6)
        
        # 模拟滚动触发懒加载
        await page.evaluate("window.scrollBy(0, 1200)")
        await human_delay(2, 4)
        await page.evaluate("window.scrollBy(0, 800)")
        await human_delay(2, 4)

        # 提取产品
        products = await page.locator('div[data-component-type="s-search-result"]').all()
        print(f"第一页获取产品数量:{len(products)}")
        assin_list = []
        for product in products:
            try:
                asin = await product.get_attribute("data-asin")
                print("asin:", asin)

                if not asin or len(asin) < 8:
                    print("continue excute")
                    continue
                assin_list.append({
                    "asin": asin.strip(),
                    "keyword": keyword,
                    "page": page_num,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception:
                continue  # 单个产品失败不影响整体

        print(f"  ✓ 成功提取 {len(assin_list)} 个产品")
        return assin_list

    except Exception as e:
        print(f"  ✗ 页面加载失败: {e}")
        return []


async def main():
    all_results = []

    # 正确写法
    async with Stealth().use_async(async_playwright()) as playwright:

        browser = await playwright.chromium.launch(
            headless=False,
            # proxy=None
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        page = await context.new_page()

        # 资源拦截
        await page.route("**/*", block_resources)

        for keyword in KEYWORDS:
            print(f"\n开始爬取关键词: {keyword}")

            for page_num in range(1, MAX_PAGES_PER_KEYWORD + 1):
                try:
                    print(f"正在爬取第 {page_num} 页...")

                    data = await scrape_search_page(
                        page,
                        keyword,
                        page_num
                    )

                    all_results.extend(data)

                    print(f"当前累计数据量: {len(all_results)}")

                    # 模拟真人延迟
                    await human_delay()

                except Exception as e:
                    print(
                        f"关键词 {keyword} "
                        f"第 {page_num} 页异常: {e}"
                    )

                    await human_delay(15, 25)
                    continue

        await browser.close()

    # 保存结果
    output_path = Path(OUTPUT_FILE)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            all_results,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"\n🎉 爬取完成！共获取 {len(all_results)} 条记录")
    print(f"文件已保存至: {output_path.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())

