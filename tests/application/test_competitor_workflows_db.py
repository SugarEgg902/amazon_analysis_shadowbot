import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path

@pytest.mark.asyncio
async def test_amazon_workflow_calls_upsert_product():
    from mp_agent.application.competitor_workflows import run_amazon_competitor_analysis

    mock_product = {
        "asin": "B001TEST", "title": "Test Product", "price": "$29.99",
        "rating": 4.5, "review_count": 100, "url": "https://amazon.com/dp/B001TEST",
        "bsr_display": "", "monthly_sales_range": "", "monthly_sales_estimate": 0,
        "monthly_revenue_estimate": 0, "bullets": [],
    }
    mock_review = {"pros": [], "cons": [], "overall": "good"}
    mock_row = {
        "ASIN": "B001TEST", "核心卖点": "test", "优点评炼": [], "缺点评炼": [],
        "综合分析": "", "竞品定位": "", "价格": "$29.99", "评分": 4.5,
        "月销量估算值": 0, "月销售额估算": 0,
    }

    with patch("mp_agent.application.competitor_workflows.scrape_amazon_products", return_value=[mock_product]), \
         patch("mp_agent.application.competitor_workflows.summarize_reviews", return_value=mock_review), \
         patch("mp_agent.application.competitor_workflows.build_analysis_row", return_value=mock_row), \
         patch("mp_agent.application.competitor_workflows.write_analysis_csv", return_value=Path("/tmp/test.csv")), \
         patch("mp_agent.application.competitor_workflows.product_exists", new_callable=AsyncMock, return_value=False), \
         patch("mp_agent.application.competitor_workflows.upsert_product", new_callable=AsyncMock, return_value=1) as mock_upsert, \
         patch("mp_agent.application.competitor_workflows.save_detail", new_callable=AsyncMock), \
         patch("mp_agent.application.competitor_workflows.save_snapshot", new_callable=AsyncMock), \
         patch("mp_agent.application.competitor_workflows.save_analysis_result", new_callable=AsyncMock), \
         patch("mp_agent.application.competitor_workflows.schedule_matching"):
        emit = AsyncMock()
        result = await run_amazon_competitor_analysis("doogee", 1, emit)
        mock_upsert.assert_called_once()
        assert result["platform"] == "amazon"
