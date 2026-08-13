"""Add language preferences and canonical language metadata to materials."""

from alembic import op
import sqlalchemy as sa


revision = "20260812_04"
down_revision = "20260811_03"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    bind = op.get_bind()
    material_columns = _columns("material")
    # The checks make restarting after an interrupted SQLite migration safe.
    if "content_language" not in material_columns:
        op.add_column(
            "material",
            sa.Column("content_language", sa.String(), nullable=False, server_default="en"),
        )
    if "translation_language" not in material_columns:
        op.add_column(
            "material",
            sa.Column("translation_language", sa.String(), nullable=False, server_default="zh-CN"),
        )
    bind.execute(sa.text("UPDATE material SET content_language = 'en' WHERE content_language IS NULL OR content_language = ''"))
    bind.execute(sa.text("UPDATE material SET translation_language = 'zh-CN' WHERE translation_language IS NULL OR translation_language = ''"))
    bind.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_material_content_language ON material (content_language)"))
    bind.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_material_translation_language ON material (translation_language)"))

    inspector = sa.inspect(bind)
    if "learning_language_preferences" not in inspector.get_table_names():
        op.create_table(
            "learning_language_preferences",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ui_locale", sa.String(), nullable=False, server_default="zh-CN"),
            sa.Column("learning_language", sa.String(), nullable=False, server_default="en"),
            sa.Column("translation_language", sa.String(), nullable=False, server_default="zh-CN"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("learning_language_preferences")
    # SQLite cannot drop material columns without rebuilding a user database.
