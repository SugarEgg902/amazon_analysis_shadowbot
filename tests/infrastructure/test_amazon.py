import asyncio
import sys
import types

import pytest

sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=object))
sys.modules.setdefault(
    "playwright.async_api",
    types.SimpleNamespace(async_playwright=object),
)
sys.modules.setdefault(
    "playwright_stealth",
    types.SimpleNamespace(Stealth=object),
)

from mp_agent.infrastructure import amazon as amazon_tools


def test_write_single_cell_xlsx_round_trip(tmp_path):
    path = tmp_path / "asin_list.xlsx"
    amazon_tools._write_single_cell_xlsx(str(path), "https://example.com/reviews")

    rows = amazon_tools._read_xlsx_rows(str(path))

    assert rows == [["https://example.com/reviews"]]


def test_parse_best_sellers_rank_extracts_primary_category_and_rank():
    rank_text = "#3,214 in Cell Phones & Accessories (See Top 100 in Cell Phones & Accessories)"

    result = amazon_tools._parse_best_sellers_rank(rank_text)

    assert result == {
        "bsr_rank": 3214,
        "bsr_category": "Cell Phones & Accessories",
        "bsr_display": "#3,214 in Cell Phones & Accessories",
    }


def test_parse_best_sellers_rank_prefers_supported_category_over_subcategory():
    rank_text = (
        "Amazon Best Sellers Rank "
        "#8 in Unlocked Cell Phones (See Top 100 in Cell Phones & Accessories) "
        "#287 in Cell Phones & Accessories"
    )

    result = amazon_tools._parse_best_sellers_rank(rank_text)

    assert result == {
        "bsr_rank": 287,
        "bsr_category": "Cell Phones & Accessories",
        "bsr_display": "#287 in Cell Phones & Accessories",
    }


def test_extract_best_sellers_rank_falls_back_to_body_text_when_sections_miss():
    class _Locator:
        def __init__(self, text="", count=1):
            self._text = text
            self._count = count
            self.first = self

        async def count(self):
            return self._count

        async def inner_text(self, timeout=0):
            return self._text

    class _Page:
        def locator(self, selector):
            if selector == "body":
                return _Locator(
                    "Product information Amazon Best Sellers Rank "
                    "#1,234 in Electronics (See Top 100 in Electronics)"
                )
            return _Locator("", 0)

    result = asyncio.run(amazon_tools._extract_best_sellers_rank(_Page()))

    assert result == {
        "bsr_rank": 1234,
        "bsr_category": "Electronics",
        "bsr_display": "#1,234 in Electronics",
    }


def test_extract_best_sellers_rank_reads_detail_bullet_spans():
    class _Locator:
        def __init__(self, texts=None, count=None):
            self._texts = list(texts or [])
            self._count = len(self._texts) if count is None else count
            self.first = self

        async def count(self):
            return self._count

        async def inner_text(self, timeout=0):
            return self._texts[0] if self._texts else ""

        async def all_inner_texts(self):
            return list(self._texts)

    class _Page:
        def locator(self, selector):
            if selector == "#detailBullets_feature_div span.a-list-item":
                return _Locator(
                    [
                        "Brand Blackview",
                        "Best Sellers Rank #2,345 in Electronics (See Top 100 in Electronics)",
                    ]
                )
            if selector == "body":
                return _Locator([""])
            return _Locator([], 0)

    result = asyncio.run(amazon_tools._extract_best_sellers_rank(_Page()))

    assert result == {
        "bsr_rank": 2345,
        "bsr_category": "Electronics",
        "bsr_display": "#2,345 in Electronics",
    }


def test_extract_best_sellers_rank_reads_expander_table_spans():
    class _Locator:
        def __init__(self, texts=None, count=None):
            self._texts = list(texts or [])
            self._count = len(self._texts) if count is None else count
            self.first = self

        async def count(self):
            return self._count

        async def inner_text(self, timeout=0):
            return self._texts[0] if self._texts else ""

        async def all_inner_texts(self):
            return list(self._texts)

    class _Page:
        def locator(self, selector):
            if selector == "#productDetails_expanderTables_depthRightSections span.a-list-item":
                return _Locator(
                    [
                        "Item model number BV9300",
                        "#12,345 in Cell Phones & Accessories (See Top 100 in Cell Phones & Accessories)",
                    ]
                )
            if selector == "body":
                return _Locator([""])
            return _Locator([], 0)

    result = asyncio.run(amazon_tools._extract_best_sellers_rank(_Page()))

    assert result == {
        "bsr_rank": 12345,
        "bsr_category": "Cell Phones & Accessories",
        "bsr_display": "#12,345 in Cell Phones & Accessories",
    }


def test_estimate_monthly_sales_uses_category_band_midpoint():
    estimate = amazon_tools._estimate_monthly_sales(
        "Electronics",
        2500,
    )

    assert estimate == {
        "monthly_sales_range": "200-1000",
        "monthly_sales_estimate": 600,
    }


def test_estimate_monthly_sales_returns_none_for_unknown_category():
    estimate = amazon_tools._estimate_monthly_sales(
        "Home & Kitchen",
        2500,
    )

    assert estimate == {
        "monthly_sales_range": "",
        "monthly_sales_estimate": "",
    }


def test_rows_to_review_dicts_maps_headerless_review_rows():
    rows = [
        [
            "Aric M Gnesa",
            "Excellent phone!",
            "Reviewed in the United States on April 8, 2026",
            "A great rugged phone with strong battery life.",
            "5.0 out of 5 stars",
        ],
        [
            "Jeana",
            "Battery life is short",
            "Reviewed in the United States on April 26, 2026",
            "The battery does not last all day.",
            "3.0 out of 5 stars",
        ],
    ]

    result = amazon_tools._rows_to_review_dicts(rows)

    assert result == [
        {
            "author_name": "Aric M Gnesa",
            "review_header": "Excellent phone!",
            "review_posted_date": "Reviewed in the United States on April 8, 2026",
            "review_text": "A great rugged phone with strong battery life.",
            "rating": "5.0 out of 5 stars",
        },
        {
            "author_name": "Jeana",
            "review_header": "Battery life is short",
            "review_posted_date": "Reviewed in the United States on April 26, 2026",
            "review_text": "The battery does not last all day.",
            "rating": "3.0 out of 5 stars",
        },
    ]


def test_summarize_reviews_uses_excel_flow_and_summarizes(monkeypatch):
    sample_reviews = [
        {
            "asin": "B07TGQP8G1",
            "rating": 5,
            "review_id": "R1",
            "review_header": "Great brush",
            "review_text": "Battery life is strong and cleans well.",
            "helpful_count": 10,
        },
        {
            "asin": "B07TGQP8G1",
            "rating": 4,
            "review_id": "R2",
            "review_header": "Works well",
            "review_text": "Good cleaning and comfortable handle.",
            "helpful_count": 4,
        },
        {
            "asin": "B07TGQP8G1",
            "rating": 2,
            "review_id": "R3",
            "review_header": "Stopped charging",
            "review_text": "It failed after a few months of use.",
            "helpful_count": 7,
        },
        {
            "asin": "B07TGQP8G1",
            "rating": 3,
            "review_id": "R4",
            "review_header": "Average",
            "review_text": "Not bad, not great.",
            "helpful_count": 1,
        },
    ]
    captured = {"writes": []}

    def fake_write(path, value):
        captured["writes"].append((path, value))

    async def fake_wait(path, poll_interval_sec, timeout_sec):
        captured["wait_args"] = (path, poll_interval_sec, timeout_sec)
        return sample_reviews

    def fake_summary(positive, negative):
        captured["positive"] = positive
        captured["negative"] = negative
        return {
            "pros": ["清洁力强", "手柄握持舒服"],
            "cons": ["续航或充电可靠性一般"],
            "overall": "整体体验较好，但耐用性有风险。",
        }

    monkeypatch.setattr(amazon_tools, "_write_single_cell_xlsx", fake_write)
    monkeypatch.setattr(amazon_tools, "_wait_for_reviews_xlsx", fake_wait)
    monkeypatch.setattr(amazon_tools, "_llm_summarize", fake_summary)

    result = asyncio.run(amazon_tools.summarize_reviews("B07TGQP8G1", max_reviews=100))

    assert captured["writes"] == [
        (
            amazon_tools.ASIN_LIST_XLSX_PATH,
            "https://www.amazon.com/product-reviews/B07TGQP8G1/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews",
        ),
        (
            amazon_tools.ASIN_LIST_XLSX_PATH,
            "",
        ),
        (
            amazon_tools.ALL_REVIEWS_XLSX_PATH,
            "",
        ),
    ]
    assert captured["wait_args"] == (
        amazon_tools.ALL_REVIEWS_XLSX_PATH,
        amazon_tools.XLSX_POLL_INTERVAL_SEC,
        amazon_tools.XLSX_POLL_TIMEOUT_SEC,
    )
    assert len(captured["positive"]) == 2
    assert len(captured["negative"]) == 1
    assert result["asin"] == "B07TGQP8G1"
    assert result["review_count"] == 4
    assert result["positive_count"] == 2
    assert result["negative_count"] == 1
    assert result["neutral_count"] == 1
    assert result["reviews"] == sample_reviews
    assert result["pros"] == ["清洁力强", "手柄握持舒服"]
    assert result["cons"] == ["续航或充电可靠性一般"]
    assert result["overall"] == "整体体验较好，但耐用性有风险。"


def test_summarize_reviews_clears_excel_files_when_wait_fails(monkeypatch):
    captured = {"writes": []}

    def fake_write(path, value):
        captured["writes"].append((path, value))

    async def fake_wait(path, poll_interval_sec, timeout_sec):
        raise TimeoutError("review file never arrived")

    monkeypatch.setattr(amazon_tools, "_write_single_cell_xlsx", fake_write)
    monkeypatch.setattr(amazon_tools, "_wait_for_reviews_xlsx", fake_wait)

    with pytest.raises(TimeoutError, match="review file never arrived"):
        asyncio.run(amazon_tools.summarize_reviews("B07TGQP8G1", max_reviews=100))

    assert captured["writes"] == [
        (
            amazon_tools.ASIN_LIST_XLSX_PATH,
            "https://www.amazon.com/product-reviews/B07TGQP8G1/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews",
        ),
        (amazon_tools.ASIN_LIST_XLSX_PATH, ""),
        (amazon_tools.ALL_REVIEWS_XLSX_PATH, ""),
    ]


def test_summarize_reviews_serializes_fixed_excel_handshake(monkeypatch):
    writes = []
    first_wait_started = asyncio.Event()
    allow_first_wait_to_finish = asyncio.Event()
    second_wait_started = asyncio.Event()
    wait_call_count = 0

    def fake_write(path, value):
        writes.append((path, value))

    async def fake_wait(path, poll_interval_sec, timeout_sec):
        nonlocal wait_call_count
        wait_call_count += 1
        if wait_call_count == 1:
            first_wait_started.set()
            await allow_first_wait_to_finish.wait()
            return [{"asin": "ASIN-1", "rating": 5, "review_text": "Excellent"}]
        second_wait_started.set()
        return [{"asin": "ASIN-2", "rating": 1, "review_text": "Bad"}]

    def fake_summary(positive, negative):
        return {"pros": [], "cons": [], "overall": ""}

    monkeypatch.setattr(amazon_tools, "_write_single_cell_xlsx", fake_write)
    monkeypatch.setattr(amazon_tools, "_wait_for_reviews_xlsx", fake_wait)
    monkeypatch.setattr(amazon_tools, "_llm_summarize", fake_summary)

    async def runner():
        first = asyncio.create_task(amazon_tools.summarize_reviews("ASIN-1"))
        await first_wait_started.wait()
        second = asyncio.create_task(amazon_tools.summarize_reviews("ASIN-2"))
        await asyncio.sleep(0)

        assert writes == [
            (
                amazon_tools.ASIN_LIST_XLSX_PATH,
                "https://www.amazon.com/product-reviews/ASIN-1/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews",
            )
        ]
        assert not second_wait_started.is_set()

        allow_first_wait_to_finish.set()
        first_result, second_result = await asyncio.gather(first, second)
        return first_result, second_result

    first_result, second_result = asyncio.run(runner())

    assert writes == [
        (
            amazon_tools.ASIN_LIST_XLSX_PATH,
            "https://www.amazon.com/product-reviews/ASIN-1/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews",
        ),
        (amazon_tools.ASIN_LIST_XLSX_PATH, ""),
        (amazon_tools.ALL_REVIEWS_XLSX_PATH, ""),
        (
            amazon_tools.ASIN_LIST_XLSX_PATH,
            "https://www.amazon.com/product-reviews/ASIN-2/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews",
        ),
        (amazon_tools.ASIN_LIST_XLSX_PATH, ""),
        (amazon_tools.ALL_REVIEWS_XLSX_PATH, ""),
    ]
    assert first_result["asin"] == "ASIN-1"
    assert second_result["asin"] == "ASIN-2"
