from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import settings

BASELINE_REVISION = "20260819_01"


class IncompatibleDatabaseError(RuntimeError):
    """Raised before Alembic can write to a pre-0.4.2 database."""


def _read_existing_revision(db_path: Path) -> tuple[bool, str | None]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False, None

    connection_uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(connection_uri, uri=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not tables:
            return False, None
        if "alembic_version" not in tables:
            return True, None
        row = connection.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
        return True, str(row[0]) if row else None


def ensure_baseline_database(db_path: Path) -> None:
    """Reject legacy or unmanaged databases without changing their contents."""
    has_schema, revision = _read_existing_revision(db_path)
    if not has_schema or revision == BASELINE_REVISION:
        return

    revision_label = revision or "unversioned schema"
    raise IncompatibleDatabaseError(
        f"Database '{db_path}' uses {revision_label}, but 0.4.2 starts at "
        f"baseline {BASELINE_REVISION}. Automatic upgrade and stamp are not "
        "supported. Back up the data directory, then explicitly move or delete "
        "only the old app.db before starting again."
    )


def run_migrations() -> None:
    """Apply the current schema before workers consume durable jobs."""
    ensure_baseline_database(settings.db_path)
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
