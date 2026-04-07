from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

sqlite_url = f"sqlite:///{settings.db_path}"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False}, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
