import asyncio
import threading

from agent_service import TASKS, new_task, parse_competitor_request, run_task
from artifacts import CSV_COLUMNS


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


def _sample_row(brand: str, product: dict):
    return {
        "品牌": brand,
        "ASIN": product["asin"],
        "url": product["url"],
        "商品标题": product["title"],
        "价格": product["price"],
        "评分": product["rating"],
        "评论数": product["review_count"],
        "核心卖点": "三防机身",
        "优点评炼": "续航长",
        "缺点评炼": "偏厚重",
        "综合分析": "适合户外",
        "竞品定位": "中低价三防竞品",
    }


def _run_task(message: str):
    async def runner():
        await run_task(message, asyncio.Queue())

    asyncio.run(runner())


def test_parse_competitor_request_extracts_brand_and_count():
    parsed = parse_competitor_request("从亚马逊获取 Blackview 5 个竞品分析")

    assert parsed == {
        "platform": "amazon",
        "brand": "Blackview",
        "count": 5,
    }


def test_parse_competitor_request_allows_no_space_after_get():
    parsed = parse_competitor_request("从亚马逊获取Blackview 5 个竞品分析")

    assert parsed == {
        "platform": "amazon",
        "brand": "Blackview",
        "count": 5,
    }


def test_parse_competitor_request_rejects_invalid_prompt():
    parsed = parse_competitor_request("帮我看看这个品牌")

    assert parsed is None


def test_parse_competitor_request_rejects_partial_match():
    parsed = parse_competitor_request("请从亚马逊获取 Blackview 5 个竞品分析，谢谢")

    assert parsed is None


def test_new_task_registers_created_task():
    TASKS.clear()

    task = new_task("从亚马逊获取 Blackview 5 个竞品分析")

    assert TASKS[task.task_id] == task


def test_run_task_invalid_prompt_emits_error(monkeypatch):
    events = []

    async def fake_emit(queue, payload):
        events.append(payload)

    monkeypatch.setattr("agent_service.emit_event", fake_emit)

    _run_task("帮我看看这个品牌")

    assert events == [
        {
            "type": "error",
            "message": "请输入品牌和数量，例如：从亚马逊获取 Blackview 5 个竞品分析",
        }
    ]


def test_run_task_calls_scrape_with_brand_and_count(monkeypatch, tmp_path):
    events = []
    captured = {}
    product = _sample_product()
    row = _sample_row("Blackview", product)

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(brand, max_pages=2, max_valid=5, headless=False):
        captured["scrape"] = {
            "brand": brand,
            "max_pages": max_pages,
            "max_valid": max_valid,
            "headless": headless,
        }
        return [product]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row(**kwargs):
        return row

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)
    monkeypatch.setattr("agent_service.summarize_reviews", fake_reviews)
    monkeypatch.setattr("agent_service.build_analysis_row", fake_row)
    monkeypatch.setattr(
        "agent_service.write_analysis_csv",
        lambda rows, brand, count: tmp_path / "out.csv",
    )

    _run_task("从亚马逊获取 Blackview 1 个竞品分析")

    assert captured["scrape"] == {
        "brand": "Blackview",
        "max_pages": 2,
        "max_valid": 1,
        "headless": False,
    }
    assert events[-1]["type"] == "result"


def test_run_task_zero_products_emits_error(monkeypatch):
    events = []

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return []

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)

    _run_task("从亚马逊获取 Blackview 1 个竞品分析")

    assert events == [
        {"type": "status", "message": "正在抓取 Amazon 商品..."},
        {"type": "error", "message": "没有抓取到有效商品"},
    ]


def test_run_task_review_failure_degrades_and_still_returns_result(monkeypatch, tmp_path):
    events = []
    product = _sample_product()
    row = _sample_row("Blackview", product)

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [product]

    def fake_row(**kwargs):
        assert kwargs["review_summary"] == {"pros": [], "cons": [], "overall": ""}
        return row

    async def fake_reviews(_asin, max_reviews=100):
        raise RuntimeError("review worker unavailable")

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)
    monkeypatch.setattr("agent_service.build_analysis_row", fake_row)
    monkeypatch.setattr("agent_service.summarize_reviews", fake_reviews)
    monkeypatch.setattr(
        "agent_service.write_analysis_csv",
        lambda rows, brand, count: tmp_path / "out.csv",
    )

    _run_task("从亚马逊获取 Blackview 1 个竞品分析")

    assert events[0] == {"type": "status", "message": "正在抓取 Amazon 商品..."}
    assert any(event["type"] == "status" and "评论摘要失败" in event["message"] for event in events)
    assert any(event["type"] == "item" for event in events)
    assert events[-1]["type"] == "result"


def test_run_task_row_build_failure_emits_status_and_final_error(monkeypatch):
    events = []
    product = _sample_product()

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [product]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row(**kwargs):
        raise RuntimeError("llm analysis failed")

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)
    monkeypatch.setattr("agent_service.summarize_reviews", fake_reviews)
    monkeypatch.setattr("agent_service.build_analysis_row", fake_row)

    _run_task("从亚马逊获取 Blackview 1 个竞品分析")

    assert any(event["type"] == "status" and "分析生成失败" in event["message"] for event in events)
    assert events[-1] == {"type": "error", "message": "没有生成有效竞品分析结果"}


def test_run_task_result_payload_includes_preview_and_download(monkeypatch, tmp_path):
    events = []
    product = _sample_product()
    row = _sample_row("Blackview", product)

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [product]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row(**kwargs):
        return row

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)
    monkeypatch.setattr("agent_service.summarize_reviews", fake_reviews)
    monkeypatch.setattr("agent_service.build_analysis_row", fake_row)
    monkeypatch.setattr(
        "agent_service.write_analysis_csv",
        lambda rows, brand, count: tmp_path / "amazon_blackview_1_20260509_153000.csv",
    )

    _run_task("从亚马逊获取 Blackview 1 个竞品分析")

    assert events[-1] == {
        "type": "result",
        "summary": "已完成 1 个竞品分析",
        "preview_columns": CSV_COLUMNS,
        "preview_rows": [[row.get(column, "") for column in CSV_COLUMNS]],
        "download_url": "/api/download/amazon_blackview_1_20260509_153000.csv",
        "filename": "amazon_blackview_1_20260509_153000.csv",
    }


def test_run_task_csv_write_failure_emits_error(monkeypatch):
    events = []
    product = _sample_product()
    row = _sample_row("Blackview", product)

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [product]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row(**kwargs):
        return row

    def fake_write(_rows, brand, count):
        raise RuntimeError(f"cannot write csv for {brand}-{count}")

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)
    monkeypatch.setattr("agent_service.summarize_reviews", fake_reviews)
    monkeypatch.setattr("agent_service.build_analysis_row", fake_row)
    monkeypatch.setattr("agent_service.write_analysis_csv", fake_write)

    _run_task("从亚马逊获取 Blackview 1 个竞品分析")

    assert events[-1] == {"type": "error", "message": "写入 CSV 失败: cannot write csv for Blackview-1"}


def test_run_task_offloads_blocking_analysis_row_build(monkeypatch, tmp_path):
    events = []
    product = _sample_product()
    row = _sample_row("Blackview", product)
    loop_thread_id = None
    row_thread_id = None

    async def fake_emit(queue, payload):
        events.append(payload)

    async def fake_scrape(_brand, max_pages=2, max_valid=5, headless=False):
        return [product]

    async def fake_reviews(_asin, max_reviews=100):
        return {
            "pros": ["续航长"],
            "cons": ["偏厚重"],
            "overall": "适合户外使用",
        }

    def fake_row(**kwargs):
        nonlocal row_thread_id
        row_thread_id = threading.get_ident()
        return row

    monkeypatch.setattr("agent_service.emit_event", fake_emit)
    monkeypatch.setattr("agent_service.scrape_amazon_products", fake_scrape)
    monkeypatch.setattr("agent_service.summarize_reviews", fake_reviews)
    monkeypatch.setattr("agent_service.build_analysis_row", fake_row)
    monkeypatch.setattr(
        "agent_service.write_analysis_csv",
        lambda rows, brand, count: tmp_path / "out.csv",
    )

    async def runner():
        nonlocal loop_thread_id
        loop_thread_id = threading.get_ident()
        await run_task("从亚马逊获取 Blackview 1 个竞品分析", asyncio.Queue())

    asyncio.run(runner())

    assert row_thread_id is not None
    assert row_thread_id != loop_thread_id
    assert events[-1]["type"] == "result"
