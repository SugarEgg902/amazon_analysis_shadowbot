import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
import tempfile


@pytest.mark.asyncio
async def test_export_platform_csv_from_db_amazon():
    from mp_agent.infrastructure.artifacts import export_platform_csv_from_db

    mock_rows = [
        {
            "搜索词": "doogee", "ASIN": "B001TEST", "url": "https://amazon.com",
            "商品标题": "Test Product", "价格": "$29.99", "评分": 4.5, "评论数": 100,
            "总类目": "Electronics", "Best Sellers Rank": "#1", "月销量区间": "1000-2000",
            "月销量估算值": 1500, "月销售额估算": 44985,
            "核心卖点": "Rugged", "优点评炼": "Durable", "缺点评炼": "Heavy",
            "综合分析": "Good product", "竞品定位": "Mid-range",
        }
    ]
    with patch("mp_agent.infrastructure.artifacts._query_analysis_rows", new_callable=AsyncMock, return_value=mock_rows):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = await export_platform_csv_from_db("amazon", "doogee", 1, output_dir=tmpdir)
            assert path.exists()
            assert path.suffix == ".csv"
            assert "amazon" in path.name
            content = path.read_text(encoding="utf-8-sig")
            assert "ASIN" in content
            assert "B001TEST" in content


@pytest.mark.asyncio
async def test_export_platform_csv_from_db_ebay():
    from mp_agent.infrastructure.artifacts import export_platform_csv_from_db

    mock_rows = [
        {
            "搜索词": "doogee", "商品id": "123456", "url": "https://ebay.com/itm/123456",
            "商品标题": "Test eBay Product", "价格": "$25.00", "评分": 4.0,
            "总类目": "Electronics", "月销量估算值": 500, "月销售额估算": 12500,
            "核心卖点": "Good", "优点评炼": "Fast", "缺点评炼": "None",
            "综合分析": "OK", "竞品定位": "Budget",
        }
    ]
    with patch("mp_agent.infrastructure.artifacts._query_analysis_rows", new_callable=AsyncMock, return_value=mock_rows):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = await export_platform_csv_from_db("ebay", "doogee", 1, output_dir=tmpdir)
            assert path.exists()
            assert "ebay" in path.name
