"""v0.3.2 durable jobs and single-database score snapshots.

This revision is intentionally safe for a v0.3.1 SQLite file: create_all
creates newly introduced tables, then missing legacy columns are added.
"""

from alembic import op
from sqlmodel import SQLModel

import app.models  # noqa: F401

revision = "20260715_01"
down_revision = None
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {row[1] for row in op.get_bind().exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def _add_if_missing(table: str, column: str, definition: str) -> None:
    if column not in _columns(table):
        op.get_bind().exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())
    _add_if_missing("recording", "status", "VARCHAR DEFAULT 'completed'")
    _add_if_missing("recording", "error_message", "VARCHAR")
    _add_if_missing("recording", "job_id", "VARCHAR")
    _add_if_missing("material", "job_id", "VARCHAR")
    _add_if_missing("material", "processing_stage", "VARCHAR")
    _add_if_missing("material", "processing_progress", "INTEGER DEFAULT 0")
    _add_if_missing("material", "error_message", "VARCHAR")


def downgrade() -> None:
    # SQLite cannot safely drop legacy columns; preserve user data on downgrade.
    op.drop_table("job")
    op.drop_table("material_sentence_score")
