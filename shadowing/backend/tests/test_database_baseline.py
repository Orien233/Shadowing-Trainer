import importlib.util
import sqlite3
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.core.migrations import IncompatibleDatabaseError, ensure_baseline_database


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
        material_columns = {
            column["name"] for column in inspector.get_columns("material")
        }
        assert {
            "content_language",
            "translation_language",
            "processing_progress",
        }.issubset(material_columns)
        assert "text_practice_id" not in material_columns
        assert "material_id" in {
            column["name"] for column in inspector.get_columns("text_practices")
        }
        assert "material_sentence_score" not in inspector.get_table_names()
        assert "user_id" in {
            column["name"] for column in inspector.get_columns("recording")
        }
        assert "ix_recording_user_id" in {
            index["name"] for index in inspector.get_indexes("recording")
        }
        assert {
            "ix_word_collections_created_at",
            "ix_word_collections_normalized_word",
        }.issubset(
            {index["name"] for index in inspector.get_indexes("word_collections")}
        )

        baseline.downgrade()
        assert inspect(connection).get_table_names() == []


def test_old_database_is_rejected_read_only_before_migration(tmp_path: Path):
    database_path = tmp_path / "app.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)",
            ("20260811_03",),
        )
        connection.execute("CREATE TABLE preserved_user_data (value TEXT)")
        connection.execute(
            "INSERT INTO preserved_user_data (value) VALUES ('keep me')"
        )
        connection.commit()

    with pytest.raises(IncompatibleDatabaseError, match="Automatic upgrade and stamp"):
        ensure_baseline_database(database_path)

    with sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("20260811_03",)
        assert connection.execute(
            "SELECT value FROM preserved_user_data"
        ).fetchone() == ("keep me",)
