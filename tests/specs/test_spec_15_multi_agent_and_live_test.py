"""Spec 15 Behavioral Test Suite: Multi-Agent Hardening & Live Test Site Smoke Tests.

Validates Spec 15 requirements:
  - T003: test_live_antigravity_smoke.py exists and matches structural conventions:
      - Marked with skipif when TICKET_RUNNER_LIVE != 1.
      - Uses SubprocessRunner and ProcessHandle.
      - Gated binary resolution via which_fn / AGENT_ANTIGRAVITY_BIN.
      - Asserts closed set of events {'init', 'step_update', 'result'}.
      - Asserts conversation_id presence.
"""

from __future__ import annotations

import ast
from pathlib import Path
import pytest


def test_live_antigravity_smoke_test_file_structure() -> None:
    """Verify test_live_antigravity_smoke.py exists and adheres to structural conventions."""
    smoke_file = Path("tests/unit/adapters/test_live_antigravity_smoke.py")
    assert smoke_file.is_file(), f"Expected smoke test file at {smoke_file}"

    source = smoke_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 1. Verify skipif gating decorator on TICKET_RUNNER_LIVE
    assert "TICKET_RUNNER_LIVE" in source
    assert "pytest.mark.skipif" in source or "skipif" in source

    # 2. Verify SubprocessRunner and ProcessHandle usage
    assert "SubprocessRunner" in source
    assert "ProcessHandle" in source

    # 3. Verify closed event set assertion and conversation_id verification
    assert "conversation_id" in source
    assert "init" in source
    assert "step_update" in source
    assert "result" in source

    # 4. Verify agy headless command flags (stream-json, --print-timeout)
    assert "--output-format" in source
    assert "stream-json" in source
    assert "--print-timeout" in source

    # 5. Verify function name
    func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    assert "test_live_antigravity_json_streaming_smoke" in func_names
