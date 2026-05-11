import asyncio

from competitor_workflows import run_amazon_competitor_analysis
from workflow_registry import build_default_registry


def _sample_product():
    return {
        "asin": "B0TEST1234",
        "url": "https://www.amazon.com/dp/B0TEST1234",
        "title": "Blackview Example",
        "price": "$199.99",
        "rating": "4.4 out of 5 stars",
        "review_count": "321",
        "bullets": ["Rugged", "Long battery"],
    }


def _sample_row():
    return {
        "品牌": "Blackview",
        "ASIN": "B0TEST1234",
        "url": "https://www.amazon.com/dp/B0TEST1234",
        "商品标题": "Blackview Example",
        "价格": "$199.99",
        "评分": "4.4 out of 5 stars",
        "评论数": "321",
        "核心卖点": "三防机身",
        "优点评炼": "续航长",
        "缺点评炼": "偏厚重",
        "综合分析": "适合户外",
        "竞品定位": "中低价三防竞品",
    }


def test_default_registry_exposes_amazon_workflow_schema():
    registry = build_default_registry()

    schemas = registry.get_tool_schemas()

    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "run_amazon_competitor_analysis"


def test_run_amazon_competitor_analysis_emits_status_and_returns_artifact(tmp_path):
    events = []
    product = _sample_product()
    row = _sample_row()

    async def fake_emit(payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [product]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row_builder(**_kwargs):
        return row

    result = asyncio.run(
        run_amazon_competitor_analysis(
            brand="Blackview",
            count=1,
            emit=fake_emit,
            scrape_products=fake_scrape,
            summarize_reviews_fn=fake_reviews,
            build_row_fn=fake_row_builder,
            write_csv_fn=lambda rows, brand, count: tmp_path / "out.csv",
            download_url_builder=lambda path: f"/api/download/{path.name}",
        )
    )

    assert events[0] == {
        "type": "tool_status",
        "tool": "run_amazon_competitor_analysis",
        "message": "正在抓取 Amazon 商品...",
    }
    assert result["platform"] == "amazon"
    assert result["brand"] == "Blackview"
    assert result["count"] == 1
    assert result["preview_rows"] == [[row[column] for column in result["preview_columns"]]]
    assert result["filename"] == "out.csv"
    assert result["download_url"] == "/api/download/out.csv"
