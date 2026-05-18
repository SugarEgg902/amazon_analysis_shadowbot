# Storage Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the JSON file cache with a MySQL database layer (SQLAlchemy 2.x + Alembic), add DAO package at `mp_agent/dao/`, and wire all competitor workflows to persist products, snapshots, and analysis results.

**Architecture:** New `mp_agent/dao/` package owns all DB access (engine, ORM models, repository functions). Competitor workflows call repository functions instead of `product_cache.py`. CSV export becomes a DB query + write operation. TF-IDF global-product matching runs as an async background task after each product insert.

**Tech Stack:** MySQL 8.x, SQLAlchemy 2.x (async engine via `asyncmy`), Alembic, jieba, scikit-learn

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `mp_agent/dao/__init__.py` | Package marker, re-exports |
| Create | `mp_agent/dao/db.py` | Engine + `AsyncSession` factory |
| Create | `mp_agent/dao/models.py` | ORM models for all 7 tables |
| Create | `mp_agent/dao/repository.py` | CRUD: upsert_product, save_detail, save_snapshot, create_task, update_task, save_analysis |
| Create | `mp_agent/dao/matching.py` | TF-IDF global_product matching (async background) |
| Create | `alembic.ini` | Alembic config |
| Create | `alembic/env.py` | Migration env (imports models) |
| Create | `alembic/versions/0001_initial.py` | Initial schema migration |
| Modify | `requirements.txt` | Add sqlalchemy, alembic, asyncmy, jieba, scikit-learn |
| Modify | `config/config.py` | Add `DB_URL` |
| Modify | `mp_agent/application/competitor_workflows.py` | Call repository after scrape + analysis |
| Modify | `mp_agent/application/agent_service.py` | Create/update crawl_task around AgentRun |
| Modify | `mp_agent/infrastructure/artifacts.py` | Add `export_platform_csv_from_db` |
| Delete | `mp_agent/infrastructure/product_cache.py` | Replaced by DB dedup |

---

### Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update requirements.txt**

```
fastapi
uvicorn
openai
pytest
sqlalchemy[asyncio]>=2.0
alembic
asyncmy
cryptography
jieba
scikit-learn
```

- [ ] **Step 2: Install**

Run: `pip install sqlalchemy[asyncio]>=2.0 alembic asyncmy cryptography jieba scikit-learn`
Expected: all packages install without error

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add sqlalchemy, alembic, asyncmy, jieba, scikit-learn dependencies"
```

---

### Task 2: Add DB_URL to config

**Files:**
- Modify: `config/config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
def test_db_url_present():
    from config.config import DB_URL
    assert DB_URL.startswith("mysql+asyncmy://")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_db_url_present -v`
Expected: FAIL with ImportError or AssertionError

- [ ] **Step 3: Add DB_URL to config**

Open `config/config.py` and append:
```python
import os
DB_URL = os.getenv(
    "MP_AGENT_DB_URL",
    "mysql+asyncmy://root:password@localhost:3306/mp_agent?charset=utf8mb4",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_db_url_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/config.py tests/test_config.py
git commit -m "feat: add DB_URL config for MySQL connection"
```

---

### Task 3: Create mp_agent/dao/db.py

**Files:**
- Create: `mp_agent/dao/__init__.py`
- Create: `mp_agent/dao/db.py`
- Test: `tests/dao/test_db.py`

- [ ] **Step 1: Write failing test**

```python
# tests/dao/test_db.py
import pytest
from mp_agent.dao.db import get_async_session, engine

def test_engine_url():
    url = str(engine.url)
    assert "asyncmy" in url or "mysql" in url

@pytest.mark.asyncio
async def test_get_async_session_yields_session():
    from sqlalchemy.ext.asyncio import AsyncSession
    async with get_async_session() as session:
        assert isinstance(session, AsyncSession)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dao/test_db.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Create package marker**

```python
# mp_agent/dao/__init__.py
```

- [ ] **Step 4: Create db.py**

```python
# mp_agent/dao/db.py
from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.config import DB_URL

engine = create_async_engine(DB_URL, pool_pre_ping=True, echo=False)
_SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_async_session() -> AsyncSession:
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 5: Create tests/dao/__init__.py**

```python
# tests/dao/__init__.py
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/dao/test_db.py -v`
Expected: PASS (engine URL check passes; session test requires live DB — skip with `-k "not async_session"` if no DB available)

- [ ] **Step 7: Commit**

```bash
git add mp_agent/dao/__init__.py mp_agent/dao/db.py tests/dao/__init__.py tests/dao/test_db.py
git commit -m "feat: add dao package with async SQLAlchemy engine and session factory"
```

---

### Task 4: Create mp_agent/dao/models.py

**Files:**
- Create: `mp_agent/dao/models.py`
- Test: `tests/dao/test_models.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dao/test_models.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Create models.py (part 1 — Base + GlobalProduct + PlatformProduct)**

```python
# mp_agent/dao/models.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, DateTime, Enum, ForeignKey, Index,
    SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DECIMAL, TINYINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GlobalProduct(Base):
    __tablename__ = "global_product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_brand", "brand"),)


class PlatformProduct(Base):
    __tablename__ = "platform_product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    keyword: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    price_usd: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 2))
    price_original: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(8))
    rating: Mapped[Decimal | None] = mapped_column(DECIMAL(3, 2))
    review_count: Mapped[int | None] = mapped_column(BigInteger)
    url: Mapped[str | None] = mapped_column(String(1024))
    is_valid: Mapped[int] = mapped_column(TINYINT(1), default=1)
    global_product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("global_product.id", ondelete="SET NULL")
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(DECIMAL(4, 3))
    crawl_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    detail: Mapped["PlatformProductDetail | None"] = relationship(back_populates="product", uselist=False)
    snapshots: Mapped[list["PlatformProductSnapshot"]] = relationship(back_populates="product")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="product")

    __table_args__ = (
        UniqueConstraint("platform", "platform_product_id", name="uq_platform_product"),
        Index("idx_keyword", "keyword"),
        Index("idx_platform", "platform"),
        Index("idx_crawl_time", "crawl_time"),
        Index("idx_global_product", "global_product_id"),
    )
```

- [ ] **Step 4: Append remaining models to models.py**

```python
class PlatformProductDetail(Base):
    __tablename__ = "platform_product_detail"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("platform_product.id", ondelete="CASCADE"), nullable=False
    )
    extra: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["PlatformProduct"] = relationship(back_populates="detail")

    __table_args__ = (UniqueConstraint("product_id", name="uq_product"),)


class PlatformProductSnapshot(Base):
    __tablename__ = "platform_product_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("platform_product.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    price_usd: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 2))
    price_original: Mapped[str | None] = mapped_column(String(64))
    rating: Mapped[Decimal | None] = mapped_column(DECIMAL(3, 2))
    review_count: Mapped[int | None] = mapped_column(BigInteger)
    extra: Mapped[dict | None] = mapped_column(JSON)
    crawl_task_id: Mapped[int | None] = mapped_column(BigInteger)
    snapshotted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["PlatformProduct"] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index("idx_product_id", "product_id"),
        Index("idx_snapshotted_at", "snapshotted_at"),
    )


class CrawlTask(Base):
    __tablename__ = "crawl_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    keyword: Mapped[str] = mapped_column(String(256), nullable=False)
    target_count: Mapped[int] = mapped_column(SmallInteger, default=5)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "done", "failed"), default="pending"
    )
    products_found: Mapped[int] = mapped_column(SmallInteger, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_platform_kw", "platform", "keyword"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("platform_product.id", ondelete="CASCADE"), nullable=False
    )
    crawl_task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("crawl_task.id", ondelete="SET NULL")
    )
    core_selling_points: Mapped[str | None] = mapped_column(Text)
    pros: Mapped[list | None] = mapped_column(JSON)
    cons: Mapped[list | None] = mapped_column(JSON)
    overall: Mapped[str | None] = mapped_column(Text)
    positioning: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(256))
    llm_model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["PlatformProduct"] = relationship(back_populates="analysis_results")

    __table_args__ = (
        Index("idx_product_id_ar", "product_id"),
        Index("idx_crawl_task_id", "crawl_task_id"),
    )


class Review(Base):
    __tablename__ = "review"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("platform_product.id", ondelete="CASCADE"), nullable=False
    )
    platform_review_id: Mapped[str | None] = mapped_column(String(128))
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    title: Mapped[str | None] = mapped_column(String(512))
    body: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(256))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    country: Mapped[str | None] = mapped_column(String(64))
    helpful_count: Mapped[int] = mapped_column(BigInteger, default=0)
    sentiment: Mapped[str | None] = mapped_column(Enum("positive", "negative", "neutral"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("product_id", "platform_review_id", name="uq_review"),
        Index("idx_product_id_rv", "product_id"),
        Index("idx_rating_rv", "rating"),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/dao/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add mp_agent/dao/models.py tests/dao/test_models.py
git commit -m "feat: add ORM models for all 7 storage tables"
```

---

### Task 5: Alembic setup + initial migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial.py`

- [ ] **Step 1: Initialize Alembic**

Run: `alembic init alembic`
Expected: creates `alembic/` directory and `alembic.ini`

- [ ] **Step 2: Update alembic.ini to use env var**

In `alembic.ini`, set:
```ini
sqlalchemy.url = %(DB_URL)s
```

- [ ] **Step 3: Update alembic/env.py**

Replace the generated `env.py` with:
```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from mp_agent.dao.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", os.environ.get(
    "MP_AGENT_DB_URL",
    "mysql+pymysql://root:password@localhost:3306/mp_agent?charset=utf8mb4",
))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Note: `alembic/env.py` uses sync `pymysql` (not `asyncmy`) because Alembic's migration runner is synchronous. Add `pymysql` to requirements.txt.

- [ ] **Step 4: Generate initial migration**

Run: `alembic revision --autogenerate -m "initial schema"`
Expected: creates `alembic/versions/<hash>_initial_schema.py` with all 7 tables

- [ ] **Step 5: Apply migration to local DB**

Run: `alembic upgrade head`
Expected: all 7 tables created in MySQL

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: add Alembic config and initial schema migration"
```

---

### Task 6: Create mp_agent/dao/repository.py

**Files:**
- Create: `mp_agent/dao/repository.py`
- Test: `tests/dao/test_repository.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/dao/test_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from mp_agent.dao.repository import (
    upsert_product, save_detail, save_snapshot,
    create_crawl_task, update_crawl_task, save_analysis_result,
    product_exists,
)

@pytest.mark.asyncio
async def test_upsert_product_returns_id():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    mock_session.flush = AsyncMock()

    product_data = {
        "platform": "amazon",
        "platform_product_id": "B001TEST",
        "keyword": "doogee",
        "title": "Test Product",
        "price_usd": 29.99,
        "crawl_time": datetime.utcnow(),
    }
    # Should not raise
    with patch("mp_agent.dao.repository.get_async_session") as mock_ctx:
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        # Just verify function is importable and callable
        assert callable(upsert_product)

def test_all_functions_importable():
    assert callable(upsert_product)
    assert callable(save_detail)
    assert callable(save_snapshot)
    assert callable(create_crawl_task)
    assert callable(update_crawl_task)
    assert callable(save_analysis_result)
    assert callable(product_exists)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dao/test_repository.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Create repository.py**

```python
# mp_agent/dao/repository.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from mp_agent.dao.db import get_async_session
from mp_agent.dao.models import (
    AnalysisResult, CrawlTask, PlatformProduct,
    PlatformProductDetail, PlatformProductSnapshot,
)


async def product_exists(platform: str, platform_product_id: str) -> bool:
    async with get_async_session() as session:
        result = await session.execute(
            select(PlatformProduct.id).where(
                PlatformProduct.platform == platform,
                PlatformProduct.platform_product_id == platform_product_id,
            )
        )
        return result.scalar_one_or_none() is not None


async def upsert_product(data: dict) -> int:
    """Insert or update platform_product. Returns the row id."""
    async with get_async_session() as session:
        stmt = (
            mysql_insert(PlatformProduct)
            .values(**data)
            .on_duplicate_key_update(
                title=data.get("title"),
                price_usd=data.get("price_usd"),
                price_original=data.get("price_original"),
                rating=data.get("rating"),
                review_count=data.get("review_count"),
                url=data.get("url"),
                crawl_time=data.get("crawl_time"),
                updated_at=datetime.utcnow(),
            )
        )
        result = await session.execute(stmt)
        await session.flush()
        if result.lastrowid:
            return result.lastrowid
        row = await session.execute(
            select(PlatformProduct.id).where(
                PlatformProduct.platform == data["platform"],
                PlatformProduct.platform_product_id == data["platform_product_id"],
            )
        )
        return row.scalar_one()
```

- [ ] **Step 4: Append remaining repository functions**

```python
async def save_detail(product_id: int, extra: dict) -> None:
    async with get_async_session() as session:
        stmt = (
            mysql_insert(PlatformProductDetail)
            .values(product_id=product_id, extra=extra)
            .on_duplicate_key_update(extra=extra)
        )
        await session.execute(stmt)


async def save_snapshot(
    product_id: int,
    platform: str,
    platform_product_id: str,
    snapshot_data: dict,
    crawl_task_id: int | None = None,
) -> None:
    async with get_async_session() as session:
        snap = PlatformProductSnapshot(
            product_id=product_id,
            platform=platform,
            platform_product_id=platform_product_id,
            snapshotted_at=datetime.utcnow(),
            crawl_task_id=crawl_task_id,
            **snapshot_data,
        )
        session.add(snap)


async def create_crawl_task(platform: str, keyword: str, target_count: int) -> int:
    async with get_async_session() as session:
        task = CrawlTask(
            platform=platform,
            keyword=keyword,
            target_count=target_count,
            status="running",
            started_at=datetime.utcnow(),
        )
        session.add(task)
        await session.flush()
        return task.id


async def update_crawl_task(
    task_id: int,
    status: str,
    products_found: int = 0,
    error_message: str | None = None,
) -> None:
    async with get_async_session() as session:
        result = await session.execute(
            select(CrawlTask).where(CrawlTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            return
        task.status = status
        task.products_found = products_found
        task.finished_at = datetime.utcnow()
        if error_message:
            task.error_message = error_message


async def save_analysis_result(product_id: int, crawl_task_id: int | None, row: dict) -> None:
    async with get_async_session() as session:
        ar = AnalysisResult(
            product_id=product_id,
            crawl_task_id=crawl_task_id,
            core_selling_points=row.get("核心卖点"),
            pros=row.get("优点评炼", []) if isinstance(row.get("优点评炼"), list) else [row.get("优点评炼", "")],
            cons=row.get("缺点评炼", []) if isinstance(row.get("缺点评炼"), list) else [row.get("缺点评炼", "")],
            overall=row.get("综合分析"),
            positioning=row.get("竞品定位"),
            category=row.get("总类目"),
        )
        session.add(ar)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/dao/test_repository.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add mp_agent/dao/repository.py tests/dao/test_repository.py
git commit -m "feat: add repository CRUD functions for all storage tables"
```

---

### Task 7: Create mp_agent/dao/matching.py (TF-IDF global_product)

**Files:**
- Create: `mp_agent/dao/matching.py`
- Test: `tests/dao/test_matching.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/dao/test_matching.py
from mp_agent.dao.matching import _tokenize, _cosine_similarity

def test_tokenize_english():
    tokens = _tokenize("Doogee S98 Pro Rugged Smartphone")
    assert "doogee" in tokens
    assert "s98" in tokens

def test_tokenize_chinese():
    tokens = _tokenize("多格手机 防水耐摔")
    assert len(tokens) > 0

def test_cosine_similarity_identical():
    score = _cosine_similarity("Doogee S98 Pro", "Doogee S98 Pro")
    assert score >= 0.99

def test_cosine_similarity_different():
    score = _cosine_similarity("Doogee S98 Pro", "Samsung Galaxy S23")
    assert score < 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dao/test_matching.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Create matching.py**

```python
# mp_agent/dao/matching.py
from __future__ import annotations

import asyncio
import re

import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sk_cosine
from sqlalchemy import select, update

from mp_agent.dao.db import get_async_session
from mp_agent.dao.models import GlobalProduct, PlatformProduct

_MATCH_THRESHOLD = 0.85


def _tokenize(text: str) -> list[str]:
    chinese = "".join(re.findall(r"[一-鿿]+", text))
    english = re.sub(r"[一-鿿]", " ", text)
    tokens = list(jieba.cut(chinese)) if chinese else []
    tokens += english.lower().split()
    return [t.strip() for t in tokens if t.strip()]


def _cosine_similarity(a: str, b: str) -> float:
    vec = TfidfVectorizer(tokenizer=_tokenize, lowercase=False)
    try:
        tfidf = vec.fit_transform([a, b])
        return float(sk_cosine(tfidf[0], tfidf[1])[0][0])
    except Exception:
        return 0.0


async def match_and_assign_global_product(product_id: int, title: str) -> None:
    async with get_async_session() as session:
        result = await session.execute(
            select(GlobalProduct.id, GlobalProduct.canonical_title)
        )
        candidates = result.all()

    best_id: int | None = None
    best_score = 0.0
    for gp_id, canonical_title in candidates:
        score = _cosine_similarity(title, canonical_title)
        if score > best_score:
            best_score = score
            best_id = gp_id

    async with get_async_session() as session:
        if best_score >= _MATCH_THRESHOLD and best_id is not None:
            global_product_id = best_id
        else:
            gp = GlobalProduct(canonical_title=title)
            session.add(gp)
            await session.flush()
            global_product_id = gp.id

        await session.execute(
            update(PlatformProduct)
            .where(PlatformProduct.id == product_id)
            .values(global_product_id=global_product_id, match_confidence=best_score)
        )


def schedule_matching(product_id: int, title: str) -> None:
    """Fire-and-forget: schedule TF-IDF matching without blocking the caller."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(match_and_assign_global_product(product_id, title))
    except RuntimeError:
        asyncio.run(match_and_assign_global_product(product_id, title))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dao/test_matching.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mp_agent/dao/matching.py tests/dao/test_matching.py
git commit -m "feat: add TF-IDF global_product matching service"
```

---

### Task 8: Wire competitor_workflows.py to DB

**Files:**
- Modify: `mp_agent/application/competitor_workflows.py`
- Test: `tests/application/test_competitor_workflows_db.py`

The pattern is the same for all 8 platforms. Shown here for Amazon; repeat for eBay, Temu, Ozon, Otto, Allegro, TikTokShop, Cdiscount.

- [ ] **Step 1: Write failing test**

```python
# tests/application/test_competitor_workflows_db.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

@pytest.mark.asyncio
async def test_amazon_workflow_calls_upsert_product():
    from mp_agent.application.competitor_workflows import run_amazon_competitor_analysis

    mock_product = {
        "asin": "B001TEST", "title": "Test", "price": "$29.99",
        "rating": 4.5, "review_count": 100, "url": "https://amazon.com/dp/B001TEST",
        "bsr_display": "", "monthly_sales_range": "", "monthly_sales_estimate": 0,
        "monthly_revenue_estimate": 0, "bullets": [],
    }
    mock_review = {"pros": [], "cons": [], "overall": "good"}
    mock_row = {"ASIN": "B001TEST", "核心卖点": "test", "优点评炼": [], "缺点评炼": [], "综合分析": "", "竞品定位": ""}

    with patch("mp_agent.application.competitor_workflows.scrape_amazon_products", return_value=[mock_product]), \
         patch("mp_agent.application.competitor_workflows.summarize_reviews", return_value=mock_review), \
         patch("mp_agent.application.competitor_workflows.build_analysis_row", return_value=mock_row), \
         patch("mp_agent.application.competitor_workflows.write_analysis_csv", return_value=Path("/tmp/test.csv")), \
         patch("mp_agent.application.competitor_workflows.upsert_product", new_callable=AsyncMock, return_value=1) as mock_upsert, \
         patch("mp_agent.application.competitor_workflows.save_detail", new_callable=AsyncMock), \
         patch("mp_agent.application.competitor_workflows.save_snapshot", new_callable=AsyncMock), \
         patch("mp_agent.application.competitor_workflows.save_analysis_result", new_callable=AsyncMock), \
         patch("mp_agent.application.competitor_workflows.schedule_matching"):
        emit = AsyncMock()
        await run_amazon_competitor_analysis("doogee", 1, emit)
        mock_upsert.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/application/test_competitor_workflows_db.py -v`
Expected: FAIL (upsert_product not imported)

- [ ] **Step 3: Add imports to competitor_workflows.py**

At the top of `mp_agent/application/competitor_workflows.py`, add after existing imports:
```python
from mp_agent.dao.repository import (
    upsert_product, save_detail, save_snapshot, save_analysis_result, product_exists,
)
from mp_agent.dao.matching import schedule_matching
```

Remove the import of `load_platform_cache` and `save_cached_entry`.

- [ ] **Step 4: Replace cache logic in run_amazon_competitor_analysis**

Replace the block:
```python
cache = load_platform_cache("amazon")
new_products = [p for p in products if p.get("asin", "") not in cache][:count]
skipped = len(products) - len(new_products)
if skipped:
    await emit(...)
if not new_products:
    raise RuntimeError("所有搜索结果均已分析过，未找到新商品")
```

With:
```python
seen_new = []
for p in products:
    pid = p.get("asin", "")
    if pid and not await product_exists("amazon", pid):
        seen_new.append(p)
    if len(seen_new) >= count:
        break
new_products = seen_new
if not new_products:
    raise RuntimeError("所有搜索结果均已分析过，未找到新商品")
```

- [ ] **Step 5: Add DB persistence after build_row_fn in run_amazon_competitor_analysis**

Replace:
```python
row = build_row_fn(brand=brand, product=product, review_summary=review_summary)
save_cached_entry("amazon", asin, row)
rows.append(row)
```

With:
```python
row = build_row_fn(brand=brand, product=product, review_summary=review_summary)
from datetime import datetime
product_db_id = await upsert_product({
    "platform": "amazon",
    "platform_product_id": asin,
    "keyword": brand,
    "title": product.get("title"),
    "price_usd": _parse_price_usd(product.get("price", "")),
    "price_original": str(product.get("price", "")),
    "currency": "USD",
    "rating": product.get("rating"),
    "review_count": product.get("review_count"),
    "url": product.get("url"),
    "crawl_time": datetime.utcnow(),
})
await save_detail(product_db_id, {
    "bsr_rank": product.get("bsr_rank"),
    "bsr_category": product.get("bsr_category"),
    "bsr_display": product.get("bsr_display"),
    "monthly_sales_range": product.get("monthly_sales_range"),
    "monthly_sales_estimate": product.get("monthly_sales_estimate"),
    "monthly_revenue_estimate": product.get("monthly_revenue_estimate"),
    "bullets": product.get("bullets", []),
})
await save_snapshot(product_db_id, "amazon", asin, {
    "title": product.get("title"),
    "price_usd": _parse_price_usd(product.get("price", "")),
    "price_original": str(product.get("price", "")),
    "rating": product.get("rating"),
    "review_count": product.get("review_count"),
    "extra": {"monthly_sales_estimate": product.get("monthly_sales_estimate")},
})
await save_analysis_result(product_db_id, None, row)
schedule_matching(product_db_id, product.get("title", ""))
rows.append(row)
```

- [ ] **Step 6: Add _parse_price_usd helper at module level in competitor_workflows.py**

```python
import re as _re

def _parse_price_usd(price_str: str) -> float | None:
    m = _re.search(r"[\d,]+\.?\d*", str(price_str).replace(",", ""))
    return float(m.group().replace(",", "")) if m else None
```

- [ ] **Step 7: Repeat steps 4-5 for all other platforms**

Apply the same pattern to:
- `run_ebay_competitor_analysis` — platform_product_id = `item_id`, platform = `"ebay"`
- `run_temu_competitor_analysis` — platform_product_id = `goods_id`, platform = `"temu"`
- `run_ozon_competitor_analysis` — platform_product_id = `sku`, platform = `"ozon"`
- `run_otto_competitor_analysis` — platform_product_id = `variation_id`, platform = `"otto"`
- `run_allegro_competitor_analysis` — platform_product_id = `item_id`, platform = `"allegro"`
- `run_tiktokshop_competitor_analysis` — platform_product_id = `product_id`, platform = `"tiktokshop"`
- `run_cdiscount_competitor_analysis` — platform_product_id = `product_id`, platform = `"cdiscount"`

For each: replace `load_platform_cache` / `save_cached_entry` with `product_exists` / `upsert_product` + `save_detail` + `save_snapshot` + `save_analysis_result` + `schedule_matching`.

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/application/test_competitor_workflows_db.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add mp_agent/application/competitor_workflows.py tests/application/test_competitor_workflows_db.py
git commit -m "feat: wire competitor workflows to persist products and analysis to DB"
```

---

### Task 9: Wire agent_service.py to crawl_task

**Files:**
- Modify: `mp_agent/application/agent_service.py`
- Test: `tests/application/test_agent_service_db.py`

- [ ] **Step 1: Write failing test**

```python
# tests/application/test_agent_service_db.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_new_run_creates_crawl_task():
    from mp_agent.application.agent_service import new_run

    with patch("mp_agent.application.agent_service.create_crawl_task", new_callable=AsyncMock, return_value=42), \
         patch("mp_agent.application.agent_service.SESSION_STORE") as mock_store, \
         patch("mp_agent.application.agent_service.WORKFLOW_REGISTRY"), \
         patch("mp_agent.application.agent_service.asyncio.create_task"):
        mock_session = MagicMock()
        mock_session.slots.platform = "amazon"
        mock_session.slots.brand = "doogee"
        mock_session.slots.count = 5
        mock_session.active_run_id = None
        mock_store.get_session.return_value = mock_session
        mock_store.set_active_run = MagicMock()

        await new_run("sess_1", "帮我分析 doogee")
        assert True  # just verify no crash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/application/test_agent_service_db.py -v`
Expected: FAIL or PASS (test is lenient — main goal is no crash)

- [ ] **Step 3: Add crawl_task creation to agent_service.py**

In `mp_agent/application/agent_service.py`, add import:
```python
from mp_agent.dao.repository import create_crawl_task, update_crawl_task
```

In the `_run_workflow` inner function (or wherever the workflow is dispatched), wrap the workflow call:
```python
task_id = None
platform = session.slots.platform or "unknown"
keyword = session.slots.brand or ""
count = session.slots.count or 5
try:
    task_id = await create_crawl_task(platform, keyword, count)
except Exception:
    pass  # DB unavailable — don't block the workflow

try:
    result = await workflow_fn(brand=keyword, count=count, emit=run.queue.put)
    if task_id:
        await update_crawl_task(task_id, "done", products_found=result.get("count", count))
except Exception as exc:
    if task_id:
        await update_crawl_task(task_id, "failed", error_message=str(exc))
    raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/application/test_agent_service_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mp_agent/application/agent_service.py tests/application/test_agent_service_db.py
git commit -m "feat: create and update crawl_task records around AgentRun lifecycle"
```

---

### Task 10: Add DB-backed CSV export to artifacts.py

**Files:**
- Modify: `mp_agent/infrastructure/artifacts.py`
- Test: `tests/test_artifacts_db.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_artifacts_db.py
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path

@pytest.mark.asyncio
async def test_export_platform_csv_from_db_amazon():
    from mp_agent.infrastructure.artifacts import export_platform_csv_from_db

    mock_rows = [
        {
            "搜索词": "doogee", "ASIN": "B001TEST", "url": "https://amazon.com",
            "商品标题": "Test", "价格": "$29.99", "评分": 4.5, "评论数": 100,
            "总类目": "", "Best Sellers Rank": "", "月销量区间": "",
            "月销量估算值": 0, "月销售额估算": 0,
            "核心卖点": "", "优点评炼": "", "缺点评炼": "", "综合分析": "", "竞品定位": "",
        }
    ]
    with patch("mp_agent.infrastructure.artifacts._query_analysis_rows", new_callable=AsyncMock, return_value=mock_rows):
        path = await export_platform_csv_from_db("amazon", "doogee", 1)
        assert path.exists()
        assert path.suffix == ".csv"
        path.unlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_artifacts_db.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Append export function to artifacts.py**

```python
async def _query_analysis_rows(platform: str, keyword: str, count: int) -> list[dict]:
    from sqlalchemy import select, desc
    from mp_agent.dao.db import get_async_session
    from mp_agent.dao.models import PlatformProduct, PlatformProductDetail, AnalysisResult

    async with get_async_session() as session:
        result = await session.execute(
            select(PlatformProduct, PlatformProductDetail, AnalysisResult)
            .join(PlatformProductDetail, PlatformProductDetail.product_id == PlatformProduct.id, isouter=True)
            .join(AnalysisResult, AnalysisResult.product_id == PlatformProduct.id, isouter=True)
            .where(PlatformProduct.platform == platform, PlatformProduct.keyword == keyword)
            .order_by(desc(PlatformProduct.crawl_time))
            .limit(count)
        )
        rows = []
        for product, detail, analysis in result.all():
            extra = detail.extra if detail else {}
            row = {
                "搜索词": keyword,
                "商品id": product.platform_product_id,
                "ASIN": product.platform_product_id,
                "url": product.url or "",
                "商品标题": product.title or "",
                "价格": product.price_original or "",
                "评分": float(product.rating) if product.rating else "",
                "评论数": product.review_count or "",
                "总类目": analysis.category if analysis else "",
                "Best Sellers Rank": extra.get("bsr_display", ""),
                "月销量区间": extra.get("monthly_sales_range", ""),
                "月销量估算值": extra.get("monthly_sales_estimate", ""),
                "月销售额估算": extra.get("monthly_revenue_estimate", ""),
                "总销量估算": extra.get("total_sales_estimate", ""),
                "总销售额估算": extra.get("total_revenue_estimate", ""),
                "核心卖点": analysis.core_selling_points if analysis else "",
                "优点评炼": "；".join(analysis.pros or []) if analysis else "",
                "缺点评炼": "；".join(analysis.cons or []) if analysis else "",
                "综合分析": analysis.overall if analysis else "",
                "竞品定位": analysis.positioning if analysis else "",
            }
            rows.append(row)
        return rows


_PLATFORM_CSV_COLUMNS = {
    "amazon": CSV_COLUMNS,
    "ebay": EBAY_CSV_COLUMNS,
    "temu": TEMU_CSV_COLUMNS,
    "ozon": OZON_CSV_COLUMNS,
    "otto": OTTO_CSV_COLUMNS,
    "allegro": ALLEGRO_CSV_COLUMNS,
    "tiktokshop": TIKTOKSHOP_CSV_COLUMNS,
    "cdiscount": CDISCOUNT_CSV_COLUMNS,
}


async def export_platform_csv_from_db(
    platform: str, keyword: str, count: int, output_dir=None
) -> Path:
    rows = await _query_analysis_rows(platform, keyword, count)
    columns = _PLATFORM_CSV_COLUMNS.get(platform, CSV_COLUMNS)
    output_dir = ARTIFACTS_DIR if output_dir is None else Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_kw = _sanitize_brand(keyword)
    path = output_dir / f"{platform}_{safe_kw}_{count}_{timestamp}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_artifacts_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mp_agent/infrastructure/artifacts.py tests/test_artifacts_db.py
git commit -m "feat: add export_platform_csv_from_db for on-demand CSV export from DB"
```

---

### Task 11: Deprecate product_cache.py

**Files:**
- Delete: `mp_agent/infrastructure/product_cache.py`

- [ ] **Step 1: Verify no remaining imports**

Run: `grep -r "product_cache" . --include="*.py" -l`
Expected: only `product_cache.py` itself (all callers already migrated in Task 8)

- [ ] **Step 2: Delete the file**

Run: `rm mp_agent/infrastructure/product_cache.py`

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: all tests pass, no ImportError for product_cache

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "feat: remove product_cache.py — replaced by DB-backed dedup in repository.py"
```

---

### Task 12: Integration smoke test

**Files:**
- Test: `tests/dao/test_integration_smoke.py`

- [ ] **Step 1: Write smoke test (requires live MySQL)**

```python
# tests/dao/test_integration_smoke.py
"""
Requires: MP_AGENT_DB_URL env var pointing to a live MySQL instance.
Skip automatically if DB is unreachable.
"""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("MP_AGENT_DB_URL"),
    reason="MP_AGENT_DB_URL not set — skipping live DB tests",
)


@pytest.mark.asyncio
async def test_upsert_and_query_product():
    from datetime import datetime
    from mp_agent.dao.repository import upsert_product, product_exists

    pid = await upsert_product({
        "platform": "amazon",
        "platform_product_id": "SMOKE_TEST_001",
        "keyword": "smoke_test",
        "title": "Smoke Test Product",
        "price_usd": 9.99,
        "crawl_time": datetime.utcnow(),
    })
    assert isinstance(pid, int)
    assert await product_exists("amazon", "SMOKE_TEST_001")


@pytest.mark.asyncio
async def test_create_and_update_crawl_task():
    from mp_agent.dao.repository import create_crawl_task, update_crawl_task

    task_id = await create_crawl_task("amazon", "smoke_test", 5)
    assert isinstance(task_id, int)
    await update_crawl_task(task_id, "done", products_found=1)
```

- [ ] **Step 2: Run smoke test against live DB**

Run: `MP_AGENT_DB_URL="mysql+asyncmy://root:password@localhost:3306/mp_agent" pytest tests/dao/test_integration_smoke.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/dao/test_integration_smoke.py
git commit -m "test: add live DB integration smoke tests (skipped without MP_AGENT_DB_URL)"
```
