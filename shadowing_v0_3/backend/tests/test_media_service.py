from __future__ import annotations

import shutil
import subprocess

from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.services import media_service


def _read_ffmpeg_time_arg(command: list[str], flag: str) -> float:
    index = command.index(flag)
    return float(command[index + 1])


def _make_test_tmp_dir() -> Path:
    directory = Path("backend/tests/.tmp_media_service") / uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_detect_file_type_prefers_ffprobe_stream_types(monkeypatch) -> None:
    def fake_subprocess_run(command: list[str], check: bool, capture_output: bool, text: bool):
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="video\naudio\n",
            stderr="",
        )

    monkeypatch.setattr(media_service.subprocess, "run", fake_subprocess_run)

    assert media_service.detect_file_type(Path("sample.unknown")) == "video"


def test_detect_file_type_falls_back_to_extension_when_probe_fails(monkeypatch) -> None:
    def fake_subprocess_run(command: list[str], check: bool, capture_output: bool, text: bool):
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(media_service.subprocess, "run", fake_subprocess_run)

    assert media_service.detect_file_type(Path("sample.wav")) == "audio"


def test_build_video_playback_asset_retries_with_fallback_encoder(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run_media_command(command: list[str]) -> None:
        commands.append(command)
        if len(commands) == 1:
            raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(media_service, "_run_media_command", fake_run_media_command)

    output_path = media_service.build_video_playback_asset(Path("sample.mkv"))

    assert output_path == Path("sample.playback.mp4")
    assert len(commands) == 2
    assert "libx264" in commands[0]
    assert "mpeg4" in commands[1]


def test_extract_audio_segment_clamps_to_source_duration(
    monkeypatch,
) -> None:
    captured_command: list[str] | None = None

    def fake_run_media_command(command: list[str]) -> None:
        nonlocal captured_command
        captured_command = command

    monkeypatch.setattr(media_service, "_run_media_command", fake_run_media_command)

    test_tmp_dir = _make_test_tmp_dir()
    try:
        output_path = test_tmp_dir / "segments" / "clip.wav"
        media_service.extract_audio_segment(
            input_audio_path=Path("input.wav"),
            output_audio_path=output_path,
            start_time=2.99,
            end_time=3.20,
            source_audio_duration=3.0,
        )
    finally:
        shutil.rmtree(test_tmp_dir, ignore_errors=True)

    assert captured_command is not None
    safe_start = _read_ffmpeg_time_arg(captured_command, "-ss")
    safe_end = _read_ffmpeg_time_arg(captured_command, "-to")

    assert safe_start >= 0.0
    assert safe_end <= 3.0
    assert safe_end >= safe_start
    assert safe_start >= 2.99 - 1e-6
    assert abs(safe_end - 3.0) <= 1e-6


def test_build_sentence_audio_metadata_never_exceeds_source_duration(
    monkeypatch,
) -> None:
    test_tmp_dir = _make_test_tmp_dir()
    monkeypatch.setattr(settings, "data_dir", str(test_tmp_dir))
    monkeypatch.setattr(media_service, "get_audio_duration", lambda _path: 0.42)

    extraction_calls: list[dict[str, float | Path | None]] = []

    def fake_extract_audio_segment(
        input_audio_path: Path,
        output_audio_path: Path,
        start_time: float,
        end_time: float,
        source_audio_duration: float | None = None,
    ) -> None:
        extraction_calls.append(
            {
                "input_audio_path": input_audio_path,
                "output_audio_path": output_audio_path,
                "start_time": start_time,
                "end_time": end_time,
                "source_audio_duration": source_audio_duration,
            }
        )

    monkeypatch.setattr(media_service, "extract_audio_segment", fake_extract_audio_segment)

    source_duration = 3.0
    sentence_candidates = [
        {
            "display_order": 1,
            "start_time": 2.70,
            "end_time": 2.95,
            "source_text": "tail sample",
            "word_start_time": 2.72,
            "word_end_time": 2.98,
        }
    ]

    try:
        enriched = media_service.build_sentence_audio_metadata(
            input_audio_path=Path("input.wav"),
            material_id=99,
            sentence_candidates=sentence_candidates,
            source_audio_duration=source_duration,
            trailing_tail_protect_ms=300,
            trailing_pad_ms=140,
        )
    finally:
        shutil.rmtree(test_tmp_dir, ignore_errors=True)

    assert len(enriched) == 1
    only_item = enriched[0]
    assert only_item["start_time"] >= 0.0
    assert only_item["end_time"] <= source_duration
    assert only_item["clip_end_time"] <= source_duration
    assert only_item["original_end_time"] <= source_duration

    assert len(extraction_calls) == 1
    only_call = extraction_calls[0]
    assert only_call["source_audio_duration"] == source_duration
    assert float(only_call["start_time"]) >= 0.0
    assert float(only_call["end_time"]) <= source_duration


def test_build_sentence_audio_metadata_enforces_non_overlap_between_sentences(
    monkeypatch,
) -> None:
    test_tmp_dir = _make_test_tmp_dir()
    monkeypatch.setattr(settings, "data_dir", str(test_tmp_dir))
    monkeypatch.setattr(media_service, "get_audio_duration", lambda _path: 0.30)

    extraction_calls: list[dict[str, float | Path | None]] = []

    def fake_extract_audio_segment(
        input_audio_path: Path,
        output_audio_path: Path,
        start_time: float,
        end_time: float,
        source_audio_duration: float | None = None,
    ) -> None:
        extraction_calls.append(
            {
                "input_audio_path": input_audio_path,
                "output_audio_path": output_audio_path,
                "start_time": start_time,
                "end_time": end_time,
                "source_audio_duration": source_audio_duration,
            }
        )

    monkeypatch.setattr(media_service, "extract_audio_segment", fake_extract_audio_segment)

    sentence_candidates = [
        {
            "display_order": 1,
            "start_time": 0.00,
            "end_time": 1.65,
            "source_text": "first",
            "word_start_time": 0.05,
            "word_end_time": 1.60,
        },
        {
            "display_order": 2,
            "start_time": 1.40,
            "end_time": 2.30,
            "source_text": "second",
            "word_start_time": 1.45,
            "word_end_time": 2.10,
        },
    ]

    try:
        enriched = media_service.build_sentence_audio_metadata(
            input_audio_path=Path("input.wav"),
            material_id=100,
            sentence_candidates=sentence_candidates,
            source_audio_duration=2.50,
            trailing_tail_protect_ms=300,
            trailing_pad_ms=140,
        )
    finally:
        shutil.rmtree(test_tmp_dir, ignore_errors=True)

    assert len(enriched) == 2
    first_sentence = enriched[0]
    second_sentence = enriched[1]

    assert first_sentence["end_time"] <= second_sentence["start_time"]
    assert first_sentence["clip_end_time"] <= second_sentence["clip_start_time"]

    assert len(extraction_calls) == 2
    first_call = extraction_calls[0]
    second_call = extraction_calls[1]
    assert float(first_call["end_time"]) <= float(second_call["start_time"])


def test_enforce_non_overlapping_clip_bounds_applies_min_duration_when_feasible() -> None:
    clip_windows = [
        {
            "clip_start_time": 0.0,
            "clip_end_time": 1.0,
            "clip_trimmed": False,
            "clip_trim_reason": "seed",
        },
        {
            "clip_start_time": 0.9,
            "clip_end_time": 0.91,
            "clip_trimmed": False,
            "clip_trim_reason": "seed",
        },
        {
            "clip_start_time": 0.905,
            "clip_end_time": 1.2,
            "clip_trimmed": False,
            "clip_trim_reason": "seed",
        },
    ]

    media_service._enforce_non_overlapping_clip_bounds(clip_windows, media_duration=2.0)

    for window in clip_windows:
        duration = float(window["clip_end_time"]) - float(window["clip_start_time"])
        assert duration >= media_service.MIN_CLIP_DURATION_SECONDS
