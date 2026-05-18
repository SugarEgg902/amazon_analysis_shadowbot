# tests/dao/test_repository.py
from mp_agent.dao.repository import (
    upsert_product, save_detail, save_snapshot,
    create_crawl_task, update_crawl_task, save_analysis_result,
    product_exists,
)

def test_all_functions_importable():
    assert callable(upsert_product)
    assert callable(save_detail)
    assert callable(save_snapshot)
    assert callable(create_crawl_task)
    assert callable(update_crawl_task)
    assert callable(save_analysis_result)
    assert callable(product_exists)
