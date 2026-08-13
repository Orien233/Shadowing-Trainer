"""v0.4 model providers and generated-text practice data."""

from alembic import op
from sqlmodel import SQLModel

import app.models  # noqa: F401

revision = "20260715_02"
down_revision = "20260715_01"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {row[1] for row in op.get_bind().exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def _add_if_missing(table: str, column: str, definition: str) -> None:
    if column not in _columns(table):
        op.get_bind().exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())
    _add_if_missing("material", "source_type", "VARCHAR DEFAULT 'upload'")
    _add_if_missing("material", "text_practice_id", "INTEGER")
    op.get_bind().exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_material_text_practice_id ON material (text_practice_id)"
    )


def downgrade() -> None:
    # SQLite cannot safely remove columns without rebuilding the user's database.
    op.drop_table("text_practice_words")
    op.drop_table("text_practices")
    op.drop_table("asr_scene_settings")
    op.drop_table("ai_providers")
