"""initial schema

Revision ID: 314c543ff8ae
Revises: 
Create Date: 2026-05-17 19:17:17.318487

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '314c543ff8ae'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "global_product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("canonical_title", sa.String(512), nullable=False),
        sa.Column("brand", sa.String(128), nullable=True),
        sa.Column("category", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_brand", "global_product", ["brand"])

    op.create_table(
        "platform_product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_product_id", sa.String(128), nullable=False),
        sa.Column("keyword", sa.String(256), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("price_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_original", sa.String(64), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("review_count", sa.BigInteger(), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("is_valid", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("global_product_id", sa.BigInteger(), nullable=True),
        sa.Column("match_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("crawl_time", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["global_product_id"], ["global_product.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "platform_product_id", name="uq_platform_product"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_keyword", "platform_product", ["keyword"])
    op.create_index("idx_platform", "platform_product", ["platform"])
    op.create_index("idx_crawl_time", "platform_product", ["crawl_time"])
    op.create_index("idx_global_product", "platform_product", ["global_product_id"])

    op.create_table(
        "platform_product_detail",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["platform_product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_product"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "platform_product_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_product_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("price_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_original", sa.String(64), nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("review_count", sa.BigInteger(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("crawl_task_id", sa.BigInteger(), nullable=True),
        sa.Column("snapshotted_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["platform_product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_product_id", "platform_product_snapshot", ["product_id"])
    op.create_index("idx_snapshotted_at", "platform_product_snapshot", ["snapshotted_at"])

    op.create_table(
        "crawl_task",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("keyword", sa.String(256), nullable=False),
        sa.Column("target_count", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("status", sa.Enum("pending", "running", "done", "failed"), nullable=False, server_default="pending"),
        sa.Column("products_found", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_status", "crawl_task", ["status"])
    op.create_index("idx_platform_kw", "crawl_task", ["platform", "keyword"])

    op.create_table(
        "analysis_result",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("crawl_task_id", sa.BigInteger(), nullable=True),
        sa.Column("core_selling_points", sa.Text(), nullable=True),
        sa.Column("pros", sa.JSON(), nullable=True),
        sa.Column("cons", sa.JSON(), nullable=True),
        sa.Column("overall", sa.Text(), nullable=True),
        sa.Column("positioning", sa.Text(), nullable=True),
        sa.Column("category", sa.String(256), nullable=True),
        sa.Column("llm_model", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["platform_product.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crawl_task_id"], ["crawl_task.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_product_id_ar", "analysis_result", ["product_id"])
    op.create_index("idx_crawl_task_id", "analysis_result", ["crawl_task_id"])

    op.create_table(
        "review",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_review_id", sa.String(128), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("author", sa.String(256), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("helpful_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sentiment", sa.Enum("positive", "negative", "neutral"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["platform_product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "platform_review_id", name="uq_review"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_product_id_rv", "review", ["product_id"])
    op.create_index("idx_rating_rv", "review", ["rating"])


def downgrade() -> None:
    op.drop_table("review")
    op.drop_table("analysis_result")
    op.drop_table("crawl_task")
    op.drop_table("platform_product_snapshot")
    op.drop_table("platform_product_detail")
    op.drop_table("platform_product")
    op.drop_table("global_product")
