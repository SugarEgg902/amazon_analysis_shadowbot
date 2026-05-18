# tests/dao/test_models.py
from mp_agent.dao.models import (
    GlobalProduct, PlatformProduct, PlatformProductDetail,
    PlatformProductSnapshot, CrawlTask, AnalysisResult, Review,
)

def test_platform_product_has_global_product_fk():
    col = PlatformProduct.__table__.c["global_product_id"]
    assert col is not None

def test_snapshot_has_no_global_product_id():
    cols = [c.name for c in PlatformProductSnapshot.__table__.columns]
    assert "global_product_id" not in cols

def test_unique_constraint_platform_product():
    uqs = [str(c) for c in PlatformProduct.__table__.constraints]
    assert any("platform" in u and "platform_product_id" in u for u in uqs)

def test_all_7_tables_defined():
    tables = [
        GlobalProduct.__tablename__,
        PlatformProduct.__tablename__,
        PlatformProductDetail.__tablename__,
        PlatformProductSnapshot.__tablename__,
        CrawlTask.__tablename__,
        AnalysisResult.__tablename__,
        Review.__tablename__,
    ]
    assert len(tables) == 7
    assert "global_product" in tables
    assert "review" in tables
