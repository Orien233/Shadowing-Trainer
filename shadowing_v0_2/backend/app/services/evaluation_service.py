from __future__ import annotations

import json
from pathlib import Path

import librosa

from app.services.media_service import get_audio_duration
from app.services.transcription_service import transcribe_text
from app.utils.text_utils import clamp_score, similarity, token_recall

# evaluate based on ASR text + duration + pause ratio
def estimate_pause_ratio(audio_path: str) -> float:
    try:
        waveform, sample_rate = librosa.load(audio_path, sr=16000)
        non_silent = librosa.effects.split(waveform, top_db=25)
        total_active = sum((end - start) for start, end in non_silent) / sample_rate
        total_duration = max(len(waveform) / sample_rate, 1e-6)
        silence = max(total_duration - total_active, 0)
        return silence / total_duration
    except Exception:
        return 0.25

# generate feedback based on the scores, with some simple rules:
def build_feedback(
    completeness_score: int,
    fluency_score: int,
    sync_score: int,
    pronunciation_score: int,
) -> tuple[str, str]:
    weak_points = []
    if completeness_score < 70:
        weak_points.append("漏读或替换较多")
    if fluency_score < 70:
        weak_points.append("停顿稍多，整体不够连贯")
    if sync_score < 70:
        weak_points.append("语速和原句节奏还不够贴合")
    if pronunciation_score < 70:
        weak_points.append("部分词形还原度不高")

    if not weak_points:
        feedback = "整体完成度不错，内容基本完整，节奏也比较接近原句。"
        suggestion = "下一轮可以尝试在保持完整性的前提下进一步模仿连读和语调。"
    else:
        feedback = "本次跟读的主要问题：" + "；".join(weak_points) + "。"
        suggestion = "建议先慢速跟读 1-2 轮，再回到正常速度，优先保证句子完整性和停顿自然。"
    return feedback, suggestion

# evaluate the recording against the reference text and duration, returning a detailed score breakdown and feedback
def evaluate_recording(reference_text: str, reference_duration: float, recording_path: str) -> dict:
    asr_text = transcribe_text(recording_path)
    duration = get_audio_duration(Path(recording_path))

    recall = token_recall(reference_text, asr_text)
    sim = similarity(reference_text, asr_text)
    pause_ratio = estimate_pause_ratio(recording_path)

    if reference_duration <= 0:
        duration_ratio = 1.0
    else:
        duration_ratio = duration / reference_duration

    completeness_score = clamp_score(recall * 100)
    pronunciation_score = clamp_score(sim * 100)
    fluency_score = clamp_score(100 - pause_ratio * 120)
    sync_score = clamp_score(100 - abs(1 - duration_ratio) * 120)

    overall_score = clamp_score(
        completeness_score * 0.35
        + pronunciation_score * 0.30
        + fluency_score * 0.20
        + sync_score * 0.15
    )

    feedback, suggestion = build_feedback(
        completeness_score=completeness_score,
        fluency_score=fluency_score,
        sync_score=sync_score,
        pronunciation_score=pronunciation_score,
    )

    return {
        "asr_text": asr_text,
        "duration": duration,
        "completeness_score": completeness_score,
        "fluency_score": fluency_score,
        "sync_score": sync_score,
        "pronunciation_score": pronunciation_score,
        "overall_score": overall_score,
        "feedback": feedback,
        "suggestion": suggestion,
        "raw_metrics": json.dumps(
            {
                "recall": recall,
                "similarity": sim,
                "pause_ratio": pause_ratio,
                "duration_ratio": duration_ratio,
                "asr_text": asr_text,
            },
            ensure_ascii=False,
        ),
    }
