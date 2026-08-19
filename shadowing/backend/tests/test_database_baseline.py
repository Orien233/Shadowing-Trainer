import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

import app.models  # noqa: F401


BASELINE_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260819_01_v0_4_2_baseline.py"
)


def load_baseline():
    spec = importlib.util.spec_from_file_location("v0_4_2_baseline", BASELINE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v0_4_2_baseline_matches_current_metadata():
    baseline = load_baseline()
    assert baseline.revision == "20260819_01"
    assert baseline.down_revision is None

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        baseline.op = Operations(MigrationContext.configure(connection))
        baseline.upgrade()

        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == set(SQLModel.metadata.tables)
        assert {
            "content_language",
            "translation_language",
            "processing_progress",
        }.issubset(
            {column["name"] for column in inspector.get_columns("material")}
        )
        assert {
            "ix_word_collections_created_at",
            "ix_word_collections_normalized_word",
        }.issubset(
            {index["name"] for index in inspector.get_indexes("word_collections")}
        )

        baseline.downgrade()
        assert inspect(connection).get_table_names() == []
