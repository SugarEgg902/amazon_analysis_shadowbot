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
