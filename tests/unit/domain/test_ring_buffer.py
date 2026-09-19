"""Unit tests for RingBuffer domain entity (T057)."""

from datetime import datetime
import pytest

from runner.domain.ring_buffer import RingBuffer, MAX_RING_BUFFER_ENTRIES


def test_ring_buffer_initial_state() -> None:
    rb = RingBuffer()
    assert len(rb) == 0
    assert rb.entries == ()
    assert rb.lines == ()


def test_ring_buffer_valid_sources() -> None:
    rb = RingBuffer()
    rb.append("worker", "Tool: Read CONTEXT.md", timestamp="13:04:03")
    rb.append("gate", "Gatekeeper: running pytest tests/ ...", timestamp="13:07:44")
    rb.append("runner", "Authoring commit: feat(queue): defer clean-slate prompt", timestamp="13:07:50")

    assert len(rb) == 3
    assert rb.lines[0] == "13:04:03 [worker] Tool: Read CONTEXT.md"
    assert rb.lines[1] == "13:07:44 [gate  ] Gatekeeper: running pytest tests/ ..."
    assert rb.lines[2] == "13:07:50 [runner] Authoring commit: feat(queue): defer clean-slate prompt"


def test_ring_buffer_invalid_source_raises_value_error() -> None:
    rb = RingBuffer()
    with pytest.raises(ValueError, match="Invalid source 'operator'"):
        rb.append("operator", "Should fail")

    with pytest.raises(ValueError, match="Invalid source ''"):
        rb.append("", "Should fail")


def test_ring_buffer_fifo_eviction_at_capacity() -> None:
    rb = RingBuffer()
    assert MAX_RING_BUFFER_ENTRIES == 15

    for i in range(20):
        rb.append("worker", f"Action {i}", timestamp=f"12:00:{i:02d}")

    assert len(rb) == 15
    # The oldest 5 (0..4) should have been evicted; 5..19 remain in order
    assert rb.lines[0] == "12:00:05 [worker] Action 5"
    assert rb.lines[-1] == "12:00:19 [worker] Action 19"
    for idx, line in enumerate(rb.lines):
        expected_num = idx + 5
        assert line == f"12:00:{expected_num:02d} [worker] Action {expected_num}"


def test_ring_buffer_timestamp_datetime() -> None:
    rb = RingBuffer()
    dt = datetime(2026, 9, 19, 14, 30, 45)
    rb.append("runner", "Sync completed", timestamp=dt)
    assert rb.lines[0] == "14:30:45 [runner] Sync completed"


def test_ring_buffer_default_timestamp() -> None:
    rb = RingBuffer()
    rb.append("gate", "Check passed")
    assert len(rb) == 1
    assert " [gate  ] Check passed" in rb.lines[0]


def test_ring_buffer_clear() -> None:
    rb = RingBuffer()
    rb.append("runner", "Event 1")
    rb.append("worker", "Event 2")
    assert len(rb) == 2
    rb.clear()
    assert len(rb) == 0
    assert rb.lines == ()


def test_ring_buffer_iteration_and_indexing() -> None:
    rb = RingBuffer()
    rb.append("worker", "A", timestamp="10:00:00")
    rb.append("gate", "B", timestamp="10:00:01")

    items = list(rb)
    assert len(items) == 2
    assert items[0] == "10:00:00 [worker] A"
    assert items[1] == "10:00:01 [gate  ] B"
    assert rb[0] == items[0]
    assert rb[1] == items[1]
