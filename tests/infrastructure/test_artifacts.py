from datetime import datetime

import mp_agent.infrastructure.artifacts as artifacts
from mp_agent.infrastructure.artifacts import ARTIFACTS_DIR, CSV_COLUMNS, write_analysis_csv


def test_write_analysis_csv_uses_expected_header_order(tmp_path):
    path = write_analysis_csv(
        rows=[
            {
                "品牌": "Blackview",
                "ASIN": "B0TEST1234",
                "url": "https://www.amazon.com/dp/B0TEST1234",
                "商品标题": "Blackview Example",
                "价格": "$199.99",
                "评分": "4.4 out of 5 stars",
                "评论数": "321",
                "总类目": "Cell Phones & Accessories",
                "Best Sellers Rank": "#3,214 in Cell Phones & Accessories",
                "月销量区间": "200-800",
                "月销量估算值": 500,
                "月销售额估算": 99995.0,
                "核心卖点": "三防机身",
                "优点评炼": "续航长",
                "缺点评炼": "偏厚重",
                "综合分析": "适合户外",
                "竞品定位": "中低价三防竞品",
            }
        ],
        brand="Blackview",
        count=1,
        output_dir=tmp_path,
    )

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    assert CSV_COLUMNS[0] == "品牌"
    assert CSV_COLUMNS[2] == "url"
    assert "总类目" in CSV_COLUMNS
    assert "Best Sellers Rank" in CSV_COLUMNS
    assert "月销量区间" in CSV_COLUMNS
    assert "月销量估算值" in CSV_COLUMNS
    assert "月销售额估算" in CSV_COLUMNS
    assert lines[0] == ",".join(CSV_COLUMNS)
    assert "Blackview Example" in lines[1]
    assert "https://www.amazon.com/dp/B0TEST1234" in lines[1]


def test_write_analysis_csv_sanitizes_brand_and_avoids_same_second_collisions(tmp_path, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 5, 9, 12, 30, 45)

    monkeypatch.setattr(artifacts, "datetime", FixedDatetime)

    first_path = write_analysis_csv(
        rows=[{"品牌": "Blackview"}],
        brand="Black/View Pro!",
        count=2,
        output_dir=tmp_path,
    )
    second_path = write_analysis_csv(
        rows=[{"品牌": "Blackview"}],
        brand="Black/View Pro!",
        count=2,
        output_dir=tmp_path,
    )

    assert first_path.name == "amazon_black_view_pro_2_20260509_123045.csv"
    assert second_path.name == "amazon_black_view_pro_2_20260509_123045_1.csv"
    assert first_path != second_path


def test_write_analysis_csv_defaults_to_shared_artifacts_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "ARTIFACTS_DIR", tmp_path)

    path = write_analysis_csv(rows=[{"品牌": "Blackview"}], brand="Blackview", count=1)

    assert ARTIFACTS_DIR.is_absolute()
    assert path.parent == tmp_path


def test_shared_artifacts_dir_defaults_outside_repo_tree():
    assert ARTIFACTS_DIR.is_absolute()
    assert artifacts.BASE_DIR not in ARTIFACTS_DIR.parents
