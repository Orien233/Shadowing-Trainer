from __future__ import annotations

import numpy as np

from app.services.audio_embedding_service import (
    aggregate_chunk_similarities,
    split_waveform_evenly,
)


def test_aggregate_chunk_similarities() -> None:
    mean_value, min_value = aggregate_chunk_similarities([0.9, 0.5, 0.2])
    assert abs(mean_value - 0.5333333) < 1e-5
    assert min_value == 0.2


def test_split_waveform_evenly_chunks_count() -> None:
    waveform = np.arange(40, dtype=np.float32)
    chunks = split_waveform_evenly(waveform, 4)
    assert len(chunks) == 4
    assert sum(chunk.size for chunk in chunks) == waveform.size
