from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.models.evaluation import Evaluation
from app.models.job import Job
from app.models.material import Material
from app.models.recording import Recording
from app.models.sentence import Sentence
from app.models.word_collection import WordCollection
from app.models.material_sentence_score import MaterialSentenceScore
from app.models.ai_provider import AIProvider
from app.models.asr_scene_setting import ASRSceneSetting
from app.models.text_practice import TextPractice, TextPracticeWord
from app.models.learning_language_preference import LearningLanguagePreference

sqlite_url = f"sqlite:///{settings.db_path}"
engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _add_column_if_missing(connection, table_name: str, column_name: str, definition: str) -> None:
    if _column_exists(connection, table_name, column_name):
        return
    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _migrate_sentence_table() -> None:
    with engine.begin() as connection:
        _add_column_if_missing(connection, "sentence", "original_start_time", "FLOAT")
        _add_column_if_missing(connection, "sentence", "original_end_time", "FLOAT")
        _add_column_if_missing(connection, "sentence", "clip_audio_path", "VARCHAR")
        _add_column_if_missing(connection, "sentence", "clip_duration", "FLOAT")

        connection.exec_driver_sql(
            """
            UPDATE sentence
            SET original_start_time = start_time
            WHERE original_start_time IS NULL
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE sentence
            SET original_end_time = end_time
            WHERE original_end_time IS NULL
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE sentence
            SET clip_duration = CASE
                WHEN end_time > start_time THEN end_time - start_time
                ELSE 0
            END
            WHERE clip_duration IS NULL
            """
        )


def _migrate_material_table() -> None:
    with engine.begin() as connection:
        _add_column_if_missing(connection, "material", "processing_owner", "VARCHAR")
        _add_column_if_missing(connection, "material", "processing_started_at", "DATETIME")
        _add_column_if_missing(connection, "material", "processing_heartbeat_at", "DATETIME")
        _add_column_if_missing(connection, "material", "job_id", "VARCHAR")
        _add_column_if_missing(connection, "material", "processing_stage", "VARCHAR")
        _add_column_if_missing(connection, "material", "processing_progress", "INTEGER DEFAULT 0")
        _add_column_if_missing(connection, "material", "error_message", "VARCHAR")


def _migrate_recording_table() -> None:
    with engine.begin() as connection:
        _add_column_if_missing(connection, "recording", "status", "VARCHAR DEFAULT 'completed'")
        _add_column_if_missing(connection, "recording", "error_message", "VARCHAR")
        _add_column_if_missing(connection, "recording", "job_id", "VARCHAR")


def _migrate_word_collection_table() -> None:
    with engine.begin() as connection:
        # Do not rewrite display text or canonical BCP-47 tags at startup.
        # Normalized keys are created by the write service; legacy rows remain
        # queryable through case-insensitive comparisons.
        connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS ix_word_collections_created_at
            ON word_collections (created_at)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS ix_word_collections_normalized_word
            ON word_collections (normalized_word)
            """
        )


def _main_db_tables() -> list:
    return [
        Material.__table__,
        Sentence.__table__,
        Recording.__table__,
        Evaluation.__table__,
        MaterialSentenceScore.__table__,
        Job.__table__,
        WordCollection.__table__,
        AIProvider.__table__,
        ASRSceneSetting.__table__,
        TextPractice.__table__,
        TextPracticeWord.__table__,
        LearningLanguagePreference.__table__,
    ]


def init_db() -> None:
    SQLModel.metadata.create_all(engine, tables=_main_db_tables())
    _migrate_sentence_table()
    _migrate_material_table()
    _migrate_recording_table()
    _migrate_word_collection_table()


def get_session():
    with Session(engine) as session:
        yield session
