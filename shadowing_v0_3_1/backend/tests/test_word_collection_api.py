from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.words import router as words_router
from app.core.database import get_session
from app.models.word_collection import WordCollection
from app.services.word_collection_service import normalize_word_text


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=[WordCollection.__table__])

    def override_get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(words_router)
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as test_client:
        yield test_client


def test_collect_new_word_success(client: TestClient):
    response = client.post(
        "/api/words/collect",
        json={
            "material_id": 1,
            "sentence_id": 10,
            "word_text": "Wanted.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] > 0
    assert payload["word_text"] == "Wanted."
    assert payload["normalized_word"] == "wanted"
    assert payload["language"] == "en"


def test_collect_duplicate_word_returns_409(client: TestClient):
    first = client.post(
        "/api/words/collect",
        json={"material_id": 1, "sentence_id": 10, "word_text": "Wanted"},
    )
    assert first.status_code == 200

    duplicate = client.post(
        "/api/words/collect",
        json={"material_id": 1, "sentence_id": 11, "word_text": "wanted."},
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "WORD_ALREADY_COLLECTED",
        "message": "这个单词已经收藏过了",
    }


def test_get_word_collections_returns_created_at_desc(client: TestClient):
    client.post(
        "/api/words/collect",
        json={"material_id": 1, "sentence_id": 10, "word_text": "first"},
    )
    second = client.post(
        "/api/words/collect",
        json={"material_id": 1, "sentence_id": 11, "word_text": "second"},
    ).json()

    response = client.get("/api/words/collections")

    assert response.status_code == 200
    payload = response.json()
    assert [item["word_text"] for item in payload] == ["second", "first"]
    assert payload[0]["id"] == second["id"]


def test_delete_word_collection_success(client: TestClient):
    created = client.post(
        "/api/words/collect",
        json={"material_id": 1, "sentence_id": 10, "word_text": "remove"},
    ).json()

    response = client.delete(f"/api/words/collections/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": created["id"]}
    assert client.get("/api/words/collections").json() == []


def test_delete_missing_word_collection_returns_404(client: TestClient):
    response = client.delete("/api/words/collections/404")

    assert response.status_code == 404
    assert response.json()["detail"] == "Word collection not found."


def test_normalize_word_text_handles_case_and_punctuation():
    assert normalize_word_text("  Wanted. ") == "wanted"
    assert normalize_word_text('"Hello!"') == "hello"
    assert normalize_word_text("can't") == "can't"
    assert normalize_word_text("...") == ""
