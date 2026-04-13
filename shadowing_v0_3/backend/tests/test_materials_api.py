from __future__ import annotations

import shutil

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api.materials import _normalize_translations_for_sentences, get_material_audio
from app.models.material import Material


def test_normalize_translations_for_sentences_pads_missing_items() -> None:
    sentence_candidates = [
        {"source_text": "first sentence"},
        {"source_text": "second sentence"},
    ]

    normalized = _normalize_translations_for_sentences(
        sentence_candidates,
        ["first translation"],
    )

    assert normalized == [
        "first translation",
        "[Translation unavailable] second sentence",
    ]


def test_normalize_translations_for_sentences_trims_extra_items() -> None:
    sentence_candidates = [
        {"source_text": "one"},
        {"source_text": "two"},
    ]

    normalized = _normalize_translations_for_sentences(
        sentence_candidates,
        ["t1", "t2", "t3"],
    )

    assert normalized == ["t1", "t2"]


class _DummySession:
    def __init__(self, material: Material | None):
        self._material = material

    def get(self, _model, _material_id: int):
        return self._material


def _make_test_tmp_dir() -> Path:
    directory = Path("backend/tests/.tmp_materials_api")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_get_material_audio_raises_when_audio_file_missing() -> None:
    test_tmp_dir = _make_test_tmp_dir()
    try:
        missing_audio_path = test_tmp_dir / "missing.wav"
        material = Material(
            id=1,
            title="sample",
            file_type="audio",
            original_path="orig.wav",
            audio_path=str(missing_audio_path),
            status="ready",
        )
        session = _DummySession(material)

        with pytest.raises(HTTPException) as exc_info:
            get_material_audio(1, session=session)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Audio file not found."
    finally:
        shutil.rmtree(test_tmp_dir, ignore_errors=True)

def test_get_material_audio_returns_file_response_when_audio_exists() -> None:
    test_tmp_dir = _make_test_tmp_dir()
    try:
        audio_path = test_tmp_dir / "clip.wav"
        audio_path.write_bytes(b"RIFF")
        material = Material(
            id=1,
            title="sample",
            file_type="audio",
            original_path="orig.wav",
            audio_path=str(audio_path),
            status="ready",
        )
        session = _DummySession(material)

        response = get_material_audio(1, session=session)

        assert isinstance(response, FileResponse)
        assert Path(response.path) == audio_path
    finally:
        shutil.rmtree(test_tmp_dir, ignore_errors=True)
