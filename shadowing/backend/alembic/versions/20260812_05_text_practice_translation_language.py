"""Persist the translation language used by generated and imported text practice."""

from alembic import op
import sqlalchemy as sa


revision = "20260812_05"
down_revision = "20260812_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("text_practices")}
    if "translation_language" not in columns:
        op.add_column(
            "text_practices",
            sa.Column("translation_language", sa.String(), nullable=False, server_default="zh-CN"),
        )
    bind.execute(sa.text("UPDATE text_practices SET translation_language = 'zh-CN' WHERE translation_language IS NULL OR translation_language = ''"))


def downgrade() -> None:
    # Preserve user text-practice metadata on SQLite rather than rebuilding the table.
    pass
