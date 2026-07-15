from __future__ import annotations

from pathlib import Path

from app.core.database import init_db


def run_migrations() -> None:
    """Upgrade app.db before workers begin consuming durable jobs.

    The fallback keeps source checkouts usable until requirements are installed;
    normal packaged runs always use Alembic.
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        init_db()
        return
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
