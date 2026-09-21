"""Unit tests for JsonFileStatusPublisher adapter and FakeStatusPublisher test double (T067)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from runner.adapters.json_status_publisher import JsonFileStatusPublisher
from runner.domain.status_event import RunState, StatusEvent
from runner.ports.status_publisher import StatusPublisher
from tests.fakes.fake_status_publisher import FakeStatusPublisher


def test_port_conformance(tmp_path: Path) -> None:
    """Both JsonFileStatusPublisher and FakeStatusPublisher conform to StatusPublisher."""
    publisher = JsonFileStatusPublisher(tmp_path / "status.json")
    fake = FakeStatusPublisher()

    assert isinstance(publisher, StatusPublisher)
    assert isinstance(fake, StatusPublisher)


def test_publish_step_finished_writes_valid_json(tmp_path: Path) -> None:
    """Publishing a STEP_FINISHED event writes status.json with correct fields."""
    status_file = tmp_path / ".agent" / "status.json"
    publisher = JsonFileStatusPublisher(status_file)

    event = StatusEvent(
        ticket_id="T067",
        run_state=RunState.RUNNING,
        attempt=1,
        max_attempts=3,
        token_count=42000,
        token_budget=150000,
        last_step_summary="Added status publisher adapter",
        last_step_at="2026-09-21T12:00:00Z",
        last_event="STEP_FINISHED",
    )
    publisher.publish(event)

    assert status_file.is_file()
    assert not status_file.with_name("status.json.tmp").exists()

    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert data == {
        "ticket_id": "T067",
        "run_state": "running",
        "attempt": 1,
        "max_attempts": 3,
        "token_count": 42000,
        "token_budget": 150000,
        "last_step_summary": "Added status publisher adapter",
        "last_step_at": "2026-09-21T12:00:00Z",
        "last_event": "STEP_FINISHED",
    }


def test_publish_with_none_last_step_summary_serializes_as_null(tmp_path: Path) -> None:
    """last_step_summary serializes as JSON null when None, not omitted."""
    status_file = tmp_path / "status.json"
    publisher = JsonFileStatusPublisher(status_file)

    event = StatusEvent(
        ticket_id="T067",
        run_state=RunState.VERIFYING,
        attempt=1,
        max_attempts=3,
        token_count=1000,
        token_budget=150000,
        last_step_summary=None,
        last_step_at="2026-09-21T12:00:00Z",
        last_event="ATTEMPT_STARTED",
    )
    publisher.publish(event)

    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert "last_step_summary" in data
    assert data["last_step_summary"] is None
    assert data["run_state"] == "verifying"
    assert data["last_event"] == "ATTEMPT_STARTED"


def test_publish_atomic_overwrite(tmp_path: Path) -> None:
    """Publishing overwrites the previous status file atomically."""
    status_file = tmp_path / "status.json"
    publisher = JsonFileStatusPublisher(status_file)

    event1 = StatusEvent(
        ticket_id="T067",
        run_state=RunState.RUNNING,
        attempt=1,
        max_attempts=3,
        token_count=1000,
        token_budget=150000,
        last_step_summary=None,
        last_step_at="2026-09-21T12:00:00Z",
        last_event="ATTEMPT_STARTED",
    )
    publisher.publish(event1)

    event2 = StatusEvent(
        ticket_id="T067",
        run_state=RunState.DONE,
        attempt=1,
        max_attempts=3,
        token_count=2000,
        token_budget=150000,
        last_step_summary="All tests passed",
        last_step_at="2026-09-21T12:01:00Z",
        last_event="ATTEMPT_ENDED",
    )
    publisher.publish(event2)

    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert data["run_state"] == "done"
    assert data["last_step_summary"] == "All tests passed"
    assert data["last_event"] == "ATTEMPT_ENDED"


def test_atomic_write_failure_leaves_no_tmp_file(tmp_path: Path) -> None:
    """A simulated write/replace failure leaves no .tmp sidecar file."""
    status_file = tmp_path / "status.json"
    publisher = JsonFileStatusPublisher(status_file)

    event = StatusEvent(
        ticket_id="T067",
        run_state=RunState.RUNNING,
        attempt=1,
        max_attempts=3,
        token_count=1000,
        token_budget=150000,
        last_step_summary=None,
        last_step_at="2026-09-21T12:00:00Z",
        last_event="ATTEMPT_STARTED",
    )

    with patch("os.replace", side_effect=OSError("Disk write error")):
        with pytest.raises(OSError, match="Disk write error"):
            publisher.publish(event)

    assert not status_file.exists()
    assert not status_file.with_name("status.json.tmp").exists()
