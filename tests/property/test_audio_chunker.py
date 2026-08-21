from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from jamly.audio import (
    BRIDGE_SAMPLE_RATE,
    VAD_FRAME_SAMPLES,
    VadGate,
    chunk_samples,
    duration_ms,
)

samples = st.lists(st.integers(min_value=-32768, max_value=32767), max_size=4096)
budgets = st.integers(min_value=1, max_value=250)


@given(samples, budgets)
def test_chunking_preserves_every_sample_in_order(source: list[int], max_ms: int) -> None:
    flattened = [value for chunk in chunk_samples(source, max_ms) for value in chunk]
    assert flattened == source


@given(samples, budgets)
def test_no_chunk_exceeds_the_budget(source: list[int], max_ms: int) -> None:
    for chunk in chunk_samples(source, max_ms):
        assert duration_ms(len(chunk)) <= max_ms


@given(samples, budgets)
def test_total_duration_is_preserved(source: list[int], max_ms: int) -> None:
    chunks = chunk_samples(source, max_ms)
    assert sum(len(chunk) for chunk in chunks) == len(source)


@given(samples, budgets)
def test_chunk_count_is_minimal(source: list[int], max_ms: int) -> None:
    assume(source)
    chunks = chunk_samples(source, max_ms)
    per_chunk = max(1, max_ms * BRIDGE_SAMPLE_RATE // 1000)
    assert len(chunks) == -(-len(source) // per_chunk)


@given(samples, budgets)
def test_every_chunk_is_non_empty(source: list[int], max_ms: int) -> None:
    assert all(chunk for chunk in chunk_samples(source, max_ms))


@given(st.lists(samples, max_size=12))
@settings(max_examples=50)
def test_the_vad_gate_never_drops_or_reorders_a_sample(batches: list[list[int]]) -> None:
    drained: list[int] = []

    def record(frame: object) -> bool:
        import numpy as np

        drained.extend(np.asarray(frame).tolist())
        return False

    gate = VadGate(record)
    total = 0
    for batch in batches:
        gate.push(batch)
        total += len(batch)

    assert len(drained) == (total // VAD_FRAME_SAMPLES) * VAD_FRAME_SAMPLES
    assert gate.pending_samples == total - len(drained)


@given(st.lists(samples, max_size=12))
@settings(max_examples=50)
def test_the_vad_gate_only_ever_sees_full_frames(batches: list[list[int]]) -> None:
    widths: list[int] = []

    def record(frame: object) -> bool:
        import numpy as np

        widths.append(len(np.asarray(frame)))
        return False

    gate = VadGate(record)
    for batch in batches:
        gate.push(batch)

    assert set(widths) <= {VAD_FRAME_SAMPLES}
