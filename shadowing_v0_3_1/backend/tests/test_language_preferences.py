from collections.abc import Iterator
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import Column, Integer, MetaData, String, Table, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlmodel import Session, SQLModel, create_engine

from app.api.language_preferences import router as language_preferences_router
from app.api.materials import router as materials_router
from app.core.database import get_session
from app.models.learning_language_preference import LearningLanguagePreference
from app.models.material import Material
from app.models.job import Job
from app.models.text_practice import TextPractice
from app.services.language_catalog import (
    ASR_AUTO_LANGUAGE,
    UNDETERMINED_LANGUAGE,
    LanguageValidationError,
    normalize_language_tag,
    normalize_ui_locale,
)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[LearningLanguagePreference.__table__],
    )

    def override_get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(language_preferences_router)
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client


def test_language_catalog_normalizes_case_and_bcp47_separator():
    assert normalize_language_tag("EN") == "en"
    assert normalize_language_tag("zh_cn") == "zh-CN"
    assert normalize_language_tag("ZH-tw") == "zh-TW"
    assert normalize_ui_locale("en") == "en-US"
    assert normalize_ui_locale("zh_cn") == "zh-CN"
    with pytest.raises(LanguageValidationError, match="UI locale"):
        normalize_ui_locale("ja")


def test_auto_and_und_are_explicit_special_cases():
    assert normalize_language_tag("auto", allow_auto=True) == ASR_AUTO_LANGUAGE
    assert normalize_language_tag("und", allow_undetermined=True) == UNDETERMINED_LANGUAGE
    with pytest.raises(LanguageValidationError, match="ASR"):
        normalize_language_tag("auto")
    with pytest.raises(LanguageValidationError, match="unknown"):
        normalize_language_tag("und")


def test_unsupported_language_is_rejected():
    with pytest.raises(LanguageValidationError, match="Unsupported"):
        normalize_language_tag("nl")


def test_language_catalog_and_singleton_preferences_api(client: TestClient):
    catalog = client.get("/api/languages")
    assert catalog.status_code == 200
    assert {item["code"] for item in catalog.json()} == {
        "en", "zh-CN", "zh-TW", "ja", "ko", "es", "fr", "de", "it", "pt", "ru", "ar"
    }

    initial = client.get("/api/languages/preferences")
    assert initial.status_code == 200
    assert initial.json()["id"] == 1
    assert initial.json()["ui_locale"] == "zh-CN"
    assert initial.json()["learning_language"] == "en"

    updated = client.put(
        "/api/languages/preferences",
        json={
            "ui_locale": "en",
            "learning_language": "ko",
            "translation_language": "zh_tw",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == 1
    assert updated.json()["ui_locale"] == "en-US"
    assert updated.json()["translation_language"] == "zh-TW"
    assert client.get("/api/languages/preferences").json()["learning_language"] == "ko"


def test_preferences_reject_auto_and_unknown_content_language(client: TestClient):
    response = client.put(
        "/api/languages/preferences",
        json={
            "ui_locale": "auto",
            "learning_language": "en",
            "translation_language": "zh-CN",
        },
    )
    assert response.status_code == 422


def test_preferences_reject_learning_language_as_ui_locale(client: TestClient):
    response = client.put(
        "/api/languages/preferences",
        json={
            "ui_locale": "ja",
            "learning_language": "ja",
            "translation_language": "en",
        },
    )
    assert response.status_code == 422


def test_material_defaults_preserve_existing_learning_assumptions():
    material = Material(title="sample", file_type="audio", original_path="sample.wav")
    assert material.content_language == "en"
    assert material.translation_language == "zh-CN"


def test_material_upload_persists_canonical_language_snapshot(monkeypatch, tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=[Material.__table__, Job.__table__])

    async def fake_save_upload(_file, _directory):
        path = tmp_path / "sample.wav"
        path.write_bytes(b"sample")
        return path

    monkeypatch.setattr("app.api.materials.save_upload", fake_save_upload)
    monkeypatch.setattr("app.api.materials.detect_file_type", lambda _path: "audio")

    def override_get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(materials_router)
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/materials/upload",
            data={
                "title": "日本語練習",
                "content_language": "JA",
                "translation_language": "zh_tw",
            },
            files={"file": ("sample.wav", b"sample", "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json()["content_language"] == "ja"
    assert response.json()["translation_language"] == "zh-TW"
    with Session(engine) as session:
        material = session.get(Material, response.json()["id"])
        assert material is not None
        assert material.content_language == "ja"
        assert material.translation_language == "zh-TW"


def test_language_migration_upgrades_and_backfills_legacy_material_table():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    legacy_material = Table(
        "material",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String, nullable=False),
        Column("file_type", String, nullable=False),
        Column("original_path", String, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            legacy_material.insert().values(
                id=1,
                title="legacy",
                file_type="audio",
                original_path="legacy.wav",
            )
        )
        migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20260812_04_language_preferences.py"
        spec = importlib.util.spec_from_file_location("language_preferences_migration", migration_path)
        assert spec and spec.loader
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        columns = {column["name"] for column in inspect(connection).get_columns("material")}
        assert {"content_language", "translation_language"}.issubset(columns)
        row = connection.execute(
            text("SELECT content_language, translation_language FROM material WHERE id = 1")
        ).mappings().one()
        assert row == {"content_language": "en", "translation_language": "zh-CN"}
        assert "learning_language_preferences" in inspect(connection).get_table_names()


def test_text_practice_translation_language_migration_backfills_legacy_rows():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    legacy_practice = Table(
        "text_practices",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String, nullable=False),
        Column("body", String, nullable=False),
        Column("source_type", String, nullable=False),
        Column("target_language", String, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(legacy_practice.insert().values(id=1, title="legacy", body="hello", source_type="import", target_language="en"))
        migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "20260812_05_text_practice_translation_language.py"
        spec = importlib.util.spec_from_file_location("text_practice_translation_migration", migration_path)
        assert spec and spec.loader
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        row = connection.execute(text("SELECT translation_language FROM text_practices WHERE id = 1")).mappings().one()
        assert row["translation_language"] == "zh-CN"

    practice = TextPractice(title="new", body="bonjour", source_type="import", target_language="fr", translation_language="en")
    assert practice.translation_language == "en"
