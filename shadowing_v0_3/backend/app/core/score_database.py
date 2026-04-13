from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.models.material_sentence_score import MaterialSentenceScore

score_sqlite_url = f"sqlite:///{settings.score_db_path}"
score_engine = create_engine(
    score_sqlite_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)


@event.listens_for(score_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def _ensure_score_indexes() -> None:
    with score_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS ix_mss_user_material_sentence_created
            ON material_sentence_score (user_id, material_id, sentence_id, created_at)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS ix_mss_user_material_created
            ON material_sentence_score (user_id, material_id, created_at)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS ix_mss_main_db_evaluation_id
            ON material_sentence_score (main_db_evaluation_id)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS ix_mss_main_db_recording_id
            ON material_sentence_score (main_db_recording_id)
            """
        )


def init_score_db() -> None:
    SQLModel.metadata.create_all(score_engine, tables=[MaterialSentenceScore.__table__])
    _ensure_score_indexes()


def get_score_session():
    with Session(score_engine) as session:
        yield session
