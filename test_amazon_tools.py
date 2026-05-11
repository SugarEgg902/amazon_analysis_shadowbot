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

import amazon_tools


class _FakeResponse:
    def __init__(self, payload, status_code=200, text=None, json_error=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else ""
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_write_single_cell_xlsx_round_trip(tmp_path):
    path = tmp_path / "asin_list.xlsx"
    amazon_tools._write_single_cell_xlsx(str(path), "https://example.com/reviews")

    rows = amazon_tools._read_xlsx_rows(str(path))

    assert rows == [["https://example.com/reviews"]]


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


def test_fetch_brightdata_reviews_handles_snapshot_flow(monkeypatch):
    calls = []
    sample_reviews = [
        {
            "asin": "B07TGQP8G1",
            "rating": 5,
            "review_id": "R1",
            "review_header": "Great brush",
            "review_text": "Battery life is strong and cleans well.",
        }
    ]

    class FakeRequests:
        @staticmethod
        def post(url, headers=None, data=None, timeout=None):
            calls.append(("POST", url))
            return _FakeResponse(
                {
                    "snapshot_id": "s_test123",
                    "message": "still processing",
                },
                status_code=202,
            )

        @staticmethod
        def get(url, headers=None, params=None, timeout=None):
            calls.append(("GET", url))
            if url.endswith("/progress/s_test123"):
                return _FakeResponse(
                    {
                        "snapshot_id": "s_test123",
                        "dataset_id": "gd_le8e811kzy4ggddlq",
                        "status": "ready",
                    }
                )
            if url.endswith("/snapshot/s_test123"):
                return _FakeResponse(sample_reviews)
            raise AssertionError(f"unexpected GET url: {url}")

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setitem(sys.modules, "requests", FakeRequests)
    monkeypatch.setattr(amazon_tools.asyncio, "sleep", fake_sleep)

    result = asyncio.run(amazon_tools._fetch_brightdata_reviews("B07TGQP8G1", 100))

    assert result == sample_reviews
    assert calls == [
        ("POST", "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_le8e811kzy4ggddlq&notify=false&include_errors=true&format=json"),
        ("GET", "https://api.brightdata.com/datasets/v3/progress/s_test123"),
        ("GET", "https://api.brightdata.com/datasets/v3/snapshot/s_test123"),
    ]


def test_fetch_brightdata_reviews_retries_when_snapshot_download_is_still_building(monkeypatch):
    calls = []
    sample_reviews = [
        {
            "asin": "B07TGQP8G1",
            "rating": 5,
            "review_id": "R1",
            "review_header": "Great brush",
            "review_text": "Battery life is strong and cleans well.",
        }
    ]
    snapshot_downloads = iter(
        [
            {
                "status": "building",
                "message": "Snapshot is building, try again in 10s",
            },
            sample_reviews,
        ]
    )

    class FakeRequests:
        @staticmethod
        def post(url, headers=None, data=None, timeout=None):
            calls.append(("POST", url))
            return _FakeResponse({"snapshot_id": "s_test456"}, status_code=202)

        @staticmethod
        def get(url, headers=None, params=None, timeout=None):
            calls.append(("GET", url))
            if url.endswith("/progress/s_test456"):
                return _FakeResponse(
                    {
                        "snapshot_id": "s_test456",
                        "dataset_id": "gd_le8e811kzy4ggddlq",
                        "status": "ready",
                    }
                )
            if url.endswith("/snapshot/s_test456"):
                return _FakeResponse(next(snapshot_downloads))
            raise AssertionError(f"unexpected GET url: {url}")

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        return None

    monkeypatch.setitem(sys.modules, "requests", FakeRequests)
    monkeypatch.setattr(amazon_tools.asyncio, "sleep", fake_sleep)

    result = asyncio.run(amazon_tools._fetch_brightdata_reviews("B07TGQP8G1", 100))

    assert result == sample_reviews
    assert sleep_calls == [10.0]
    assert calls == [
        ("POST", "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_le8e811kzy4ggddlq&notify=false&include_errors=true&format=json"),
        ("GET", "https://api.brightdata.com/datasets/v3/progress/s_test456"),
        ("GET", "https://api.brightdata.com/datasets/v3/snapshot/s_test456"),
        ("GET", "https://api.brightdata.com/datasets/v3/snapshot/s_test456"),
    ]


def test_fetch_brightdata_reviews_parses_ndjson_from_sync_post(monkeypatch):
    ndjson_text = (
        '{"asin":"B07TGQP8G1","rating":5,"review_id":"R1","review_header":"Great","review_text":"Works well."}\n'
        '{"asin":"B07TGQP8G1","rating":1,"review_id":"R2","review_header":"Bad","review_text":"Stopped working."}\n'
    )

    class FakeRequests:
        @staticmethod
        def post(url, headers=None, data=None, timeout=None):
            return _FakeResponse(
                None,
                text=ndjson_text,
                json_error=ValueError("Extra data"),
            )

    monkeypatch.setitem(sys.modules, "requests", FakeRequests)

    result = asyncio.run(amazon_tools._fetch_brightdata_reviews("B07TGQP8G1", 100))

    assert result == [
        {
            "asin": "B07TGQP8G1",
            "rating": 5,
            "review_id": "R1",
            "review_header": "Great",
            "review_text": "Works well.",
        },
        {
            "asin": "B07TGQP8G1",
            "rating": 1,
            "review_id": "R2",
            "review_header": "Bad",
            "review_text": "Stopped working.",
        },
    ]
