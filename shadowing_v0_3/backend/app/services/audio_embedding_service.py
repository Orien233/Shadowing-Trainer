from __future__ import annotations

import logging

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Sequence

import librosa
import numpy as np


logger = logging.getLogger(__name__)
_EPSILON = 1e-8
_BACKEND_CACHE_LOCK = Lock()
_BACKEND_CACHE: dict[tuple[str, str], "_WavLMBackend"] = {}


@dataclass(frozen=True)
class ImitationMetrics:
    """Reference-based utterance similarity metrics."""

    enabled: bool
    available: bool
    model_name: str
    fallback_reason: str | None
    global_cosine: float
    chunk_cosine_mean: float
    chunk_cosine_min: float
    chunk_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp_unit(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def cosine_similarity(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    """Cosine similarity on two embeddings."""
    if vector_a.size == 0 or vector_b.size == 0:
        return 0.0
    denominator = (np.linalg.norm(vector_a) * np.linalg.norm(vector_b)) + _EPSILON
    return float(np.dot(vector_a, vector_b) / denominator)


def split_waveform_evenly(waveform: np.ndarray, chunk_count: int) -> list[np.ndarray]:
    """Split a waveform into evenly sized chunks."""
    if chunk_count <= 1:
        return [waveform]
    if waveform.size == 0:
        return []

    boundaries = np.linspace(0, waveform.size, num=chunk_count + 1, dtype=np.int64)
    chunks: list[np.ndarray] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if end <= start:
            continue
        chunks.append(waveform[start:end])
    return chunks


def aggregate_chunk_similarities(chunk_cosines: Sequence[float]) -> tuple[float, float]:
    """Aggregate per-chunk cosine similarities."""
    if not chunk_cosines:
        return 0.0, 0.0
    mean_value = float(sum(chunk_cosines) / len(chunk_cosines))
    min_value = float(min(chunk_cosines))
    return mean_value, min_value


def _load_audio_mono(audio_path: str | Path, sample_rate: int) -> tuple[np.ndarray, int]:
    waveform, loaded_sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    if waveform.size == 0:
        raise ValueError("Audio is empty.")
    return np.asarray(waveform, dtype=np.float32), int(loaded_sr)


class _WavLMBackend:
    """Thin wrapper for lazy-loaded local WavLM inference."""

    def __init__(self, model_name: str, device: str) -> None:
        import torch
        from transformers import AutoFeatureExtractor, WavLMModel

        if device == "auto":
            resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            resolved_device = device

        self._torch = torch
        self._feature_extractor = AutoFeatureExtractor.from_pretrained(model_name)
        self._model = WavLMModel.from_pretrained(model_name)
        self._device = torch.device(resolved_device)
        self._model.to(self._device)
        self._model.eval()

    def embed(self, waveform: np.ndarray, sample_rate: int) -> np.ndarray:
        inputs = self._feature_extractor(
            waveform,
            sampling_rate=sample_rate,
            return_tensors="pt",
            padding=True,
        )
        tensor_inputs = {name: tensor.to(self._device) for name, tensor in inputs.items()}
        with self._torch.no_grad():
            outputs = self._model(**tensor_inputs)
        hidden_states = outputs.last_hidden_state
        embedding = hidden_states.mean(dim=1).squeeze(0).detach().cpu().numpy()
        return np.asarray(embedding, dtype=np.float32)


def _get_wavlm_backend(model_name: str, device: str) -> _WavLMBackend:
    cache_key = (model_name, device)
    with _BACKEND_CACHE_LOCK:
        backend = _BACKEND_CACHE.get(cache_key)
        if backend is not None:
            return backend
        backend = _WavLMBackend(model_name=model_name, device=device)
        _BACKEND_CACHE[cache_key] = backend
        return backend


def _pair_chunks(
    reference_waveform: np.ndarray,
    learner_waveform: np.ndarray,
    *,
    chunk_count: int,
    min_chunk_samples: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    reference_chunks = split_waveform_evenly(reference_waveform, chunk_count)
    learner_chunks = split_waveform_evenly(learner_waveform, chunk_count)

    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for reference_chunk, learner_chunk in zip(reference_chunks, learner_chunks):
        if reference_chunk.size < min_chunk_samples or learner_chunk.size < min_chunk_samples:
            continue
        pairs.append((reference_chunk, learner_chunk))
    return pairs


def compute_imitation_metrics(
    reference_audio_path: str | None,
    learner_audio_path: str,
    *,
    enabled: bool,
    model_name: str,
    device: str = "cpu",
    sample_rate: int = 16000,
    chunk_count: int = 4,
    min_chunk_seconds: float = 0.35,
) -> ImitationMetrics:
    """Compute WavLM utterance/chunk similarity with local inference only."""
    if not enabled:
        return ImitationMetrics(
            enabled=False,
            available=False,
            model_name=model_name,
            fallback_reason="wavlm_disabled",
            global_cosine=0.0,
            chunk_cosine_mean=0.0,
            chunk_cosine_min=0.0,
            chunk_count=0,
        )

    if not reference_audio_path:
        return ImitationMetrics(
            enabled=True,
            available=False,
            model_name=model_name,
            fallback_reason="missing_reference_audio",
            global_cosine=0.0,
            chunk_cosine_mean=0.0,
            chunk_cosine_min=0.0,
            chunk_count=0,
        )

    try:
        reference_waveform, reference_sr = _load_audio_mono(reference_audio_path, sample_rate)
        learner_waveform, learner_sr = _load_audio_mono(learner_audio_path, sample_rate)
        backend = _get_wavlm_backend(model_name=model_name, device=device)
    except Exception as exc:
        logger.warning("WavLM setup/load failed, fallback to unavailable imitation metrics: %s", exc)
        return ImitationMetrics(
            enabled=True,
            available=False,
            model_name=model_name,
            fallback_reason=f"wavlm_unavailable:{type(exc).__name__}",
            global_cosine=0.0,
            chunk_cosine_mean=0.0,
            chunk_cosine_min=0.0,
            chunk_count=0,
        )

    try:
        reference_embedding = backend.embed(reference_waveform, reference_sr)
        learner_embedding = backend.embed(learner_waveform, learner_sr)
        global_cosine = _clamp_unit(cosine_similarity(reference_embedding, learner_embedding))

        min_chunk_samples = max(int(min_chunk_seconds * sample_rate), 1)
        chunk_pairs = _pair_chunks(
            reference_waveform,
            learner_waveform,
            chunk_count=max(chunk_count, 1),
            min_chunk_samples=min_chunk_samples,
        )
        chunk_cosines: list[float] = []
        for reference_chunk, learner_chunk in chunk_pairs:
            reference_chunk_embedding = backend.embed(reference_chunk, reference_sr)
            learner_chunk_embedding = backend.embed(learner_chunk, learner_sr)
            chunk_cosines.append(
                _clamp_unit(cosine_similarity(reference_chunk_embedding, learner_chunk_embedding))
            )

        chunk_cosine_mean, chunk_cosine_min = aggregate_chunk_similarities(chunk_cosines)
        if not chunk_cosines:
            chunk_cosine_mean = global_cosine
            chunk_cosine_min = global_cosine

        return ImitationMetrics(
            enabled=True,
            available=True,
            model_name=model_name,
            fallback_reason=None,
            global_cosine=global_cosine,
            chunk_cosine_mean=_clamp_unit(chunk_cosine_mean),
            chunk_cosine_min=_clamp_unit(chunk_cosine_min),
            chunk_count=len(chunk_cosines),
        )
    except Exception as exc:
        logger.warning("WavLM inference failed, fallback to unavailable imitation metrics: %s", exc)
        return ImitationMetrics(
            enabled=True,
            available=False,
            model_name=model_name,
            fallback_reason=f"wavlm_inference_error:{type(exc).__name__}",
            global_cosine=0.0,
            chunk_cosine_mean=0.0,
            chunk_cosine_min=0.0,
            chunk_count=0,
        )
