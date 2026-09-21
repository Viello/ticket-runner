"""Failure analyser and isolation probe domain service (T065).

Classifies test verification failures (HANG, ENV, CASCADE, FLAKY),
extracts error fingerprints and root failing tests, and runs
targeted isolation reruns without shell invocation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
import shlex
import subprocess
from typing import Any, Callable

LABEL_HANG: str = "HANG"
LABEL_ENV: str = "ENV"
LABEL_CASCADE: str = "CASCADE"
LABEL_FLAKY: str = "FLAKY"

FAILURE_LABELS: frozenset[str] = frozenset({
    LABEL_HANG,
    LABEL_ENV,
    LABEL_CASCADE,
    LABEL_FLAKY,
})

SUGGESTED_ACTIONS: dict[str, str] = {
    LABEL_HANG: "Run /diagnosing-bugs (§ Stuck-Test-Suite Runbook) to triage hanging test or infinite loop.",
    LABEL_ENV: "Check environment, dependencies, and imports before retrying.",
    LABEL_CASCADE: "Investigate root failing test in isolation to fix common failure class.",
    LABEL_FLAKY: "Inspect test failure trace or re-run test suite.",
}

ANSI_ESCAPE_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

PYTEST_TEST_ID_RE: re.Pattern[str] = re.compile(
    r"(?:FAILED|ERROR\s+collecting)?\s*([a-zA-Z0-9_./\\-]+\.py::[a-zA-Z0-9_:]+(?:\[[^\]\r\n]*\])?)"
)
JEST_TEST_ID_RE: re.Pattern[str] = re.compile(
    r"(?:●|✕|FAIL)?\s*([^\r\n>]+(?:\s*>\s*[^\r\n>]+)+)"
)
GO_TEST_ID_RE: re.Pattern[str] = re.compile(r"---\s*FAIL:\s*([A-Za-z0-9_]+)")
CARGO_TEST_ID_RE: re.Pattern[str] = re.compile(
    r"^test\s+([A-Za-z0-9_:]+)\s+\.\.\.\s+FAILED"
)

ENV_ERROR_PATTERNS: tuple[str, ...] = (
    "modulenotfounderror",
    "importerror",
    "command not found",
    "no module named",
    "cannot import name",
)

ERROR_CLASS_RE: re.Pattern[str] = re.compile(
    r"\b([A-Z][a-zA-Z0-9_]*(?:Error|Exception|Fault))\b"
)


@dataclass(frozen=True)
class FailureDiagnostic:
    """Consolidated diagnostic report from analysing verification failures."""

    label: str
    root_tests: list[str]
    top_errors: list[str]
    log_tail: list[str]
    isolation_output: str | None
    suggested_action: str


def strip_ansi(text: str) -> str:
    """Remove ANSI color escape sequences from text."""
    return ANSI_ESCAPE_RE.sub("", text)


def extract_test_identifiers(lines: list[str]) -> list[str]:
    """Extract unique test identifiers preserving first occurrence order."""
    seen: set[str] = set()
    result: list[str] = []

    for raw_line in lines:
        line = strip_ansi(raw_line).strip()
        if not line:
            continue

        # 1. pytest: test_file.py::test_fn
        match = PYTEST_TEST_ID_RE.search(line)
        if match:
            test_id = match.group(1).strip()
            if test_id not in seen:
                seen.add(test_id)
                result.append(test_id)
            continue

        # 2. go test: --- FAIL: TestFoo
        match = GO_TEST_ID_RE.search(line)
        if match:
            test_id = match.group(1).strip()
            if test_id not in seen:
                seen.add(test_id)
                result.append(test_id)
            continue

        # 3. cargo test: test test_name ... FAILED
        match = CARGO_TEST_ID_RE.search(line)
        if match:
            test_id = match.group(1).strip()
            if test_id not in seen:
                seen.add(test_id)
                result.append(test_id)
            continue

        # 4. jest / vitest: describe > test name
        if ">" in line and any(marker in line for marker in ("●", "✕", "FAIL", ">")):
            match = JEST_TEST_ID_RE.search(line)
            if match:
                test_id = match.group(1).strip()
                if test_id not in seen:
                    seen.add(test_id)
                    result.append(test_id)
                continue

    return result


def extract_error_fingerprints(lines: list[str]) -> list[str]:
    """Extract up to 3 unique error-class fingerprints ranked by frequency."""
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}

    for idx, raw_line in enumerate(lines):
        line = strip_ansi(raw_line)
        for match in ERROR_CLASS_RE.finditer(line):
            err = match.group(1)
            counts[err] += 1
            if err not in first_seen:
                first_seen[err] = idx

    if not counts:
        # Fallback check for FAILED / ERROR markers
        for idx, raw_line in enumerate(lines):
            line = strip_ansi(raw_line)
            if "FAILED" in line and "FAILED" not in counts:
                counts["FAILED"] += 1
                first_seen["FAILED"] = idx
            if "ERROR" in line and "ERROR" not in counts:
                counts["ERROR"] += 1
                first_seen["ERROR"] = idx

    # Sort primarily by frequency descending, secondarily by appearance index
    sorted_errors = sorted(
        counts.keys(),
        key=lambda err: (-counts[err], first_seen[err]),
    )
    return sorted_errors[:3]


def build_isolation_command(test_cmd: str, isolation_cmd: str = "") -> str | None:
    """Return the isolation rerun command template for the test runner.

    Returns the explicit ``isolation_cmd`` override if provided, or infers
    a single-test template string based on runner heuristics. Returns None
    if the runner is unrecognized.
    """
    if isolation_cmd and isolation_cmd.strip():
        return isolation_cmd.strip()

    cmd = test_cmd.strip().lower()

    if re.search(r"\bpytest\b", cmd):
        return "pytest {test_id} -x"
    if re.search(r"\bvitest\b", cmd):
        return 'npx vitest --testNamePattern "{test_name}"'
    if re.search(r"\bjest\b", cmd):
        return 'npx jest --testNamePattern "{test_name}"'
    if re.search(r"\bcargo\s+test\b", cmd):
        return "cargo test {test_name}"
    if re.search(r"\bgo\s+test\b", cmd):
        return "go test -run {test_name} ./..."

    return None


def interpolate_isolation_command(
    template: str,
    test_id: str,
    test_name: str | None = None,
    runner: str | None = None,
) -> list[str]:
    """Safely construct an argument vector without shell evaluation.

    Parses the template and substitutes variables to produce a list of argv
    tokens suitable for direct execution with ``shell=False`` (ADR 0016).
    """
    if not template or not template.strip():
        return []

    effective_test_name = test_name
    if effective_test_name is None:
        if "::" in test_id:
            effective_test_name = test_id.split("::")[-1]
        elif ">" in test_id:
            effective_test_name = test_id.split(">")[-1].strip()
        else:
            effective_test_name = test_id

    effective_runner = runner or ("vitest" if "vitest" in template else "jest")

    interpolated = template.format(
        test_id=test_id,
        test_name=effective_test_name,
        runner=effective_runner,
    )

    # Use posix=False to preserve backslashes in Windows file paths
    argv = shlex.split(interpolated, posix=False)
    # Strip any paired surrounding quotes preserved by posix=False
    cleaned_argv = [
        token[1:-1]
        if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'")
        else token
        for token in argv
    ]
    return cleaned_argv


def _check_env_failure(lines: list[str], first_test_line_idx: int | None) -> bool:
    """Check if environment/setup errors appear before the first test identifier."""
    for idx, raw_line in enumerate(lines):
        if first_test_line_idx is not None and idx >= first_test_line_idx:
            break
        lower_line = strip_ansi(raw_line).lower()
        if any(pat in lower_line for pat in ENV_ERROR_PATTERNS):
            return True
    return False


def _check_cascade_failure(lines: list[str], top_errors: list[str]) -> bool:
    """Check if 5+ failures occur sharing a repeating error class."""
    failure_entries = sum(
        1
        for raw_line in lines
        if re.search(r"\b(FAILED|ERROR)\b", strip_ansi(raw_line))
        or strip_ansi(raw_line).startswith("--- FAIL:")
    )
    if failure_entries < 5 or not top_errors:
        return False

    # Count occurrences of the top error class
    primary_err = top_errors[0]
    primary_count = sum(
        1
        for raw_line in lines
        if re.search(rf"\b{re.escape(primary_err)}\b", strip_ansi(raw_line))
    )
    return primary_count >= 5


def _run_isolation_probe(
    argv: list[str],
    timeout_seconds: int,
    probe_runner: Callable[..., Any] | None = None,
) -> str | None:
    """Execute the isolation probe subprocess without shell invocation."""
    if not argv:
        return None

    if probe_runner is not None:
        try:
            result = probe_runner(argv, timeout=timeout_seconds)
            if isinstance(result, str):
                return result
            stdout = getattr(result, "stdout", "") or ""
            stderr = getattr(result, "stderr", "") or ""
            combined = stdout + ("\n" + stderr if stderr else "")
            return combined.strip()
        except Exception as exc:
            return f"[Isolation probe error: {exc}]"

    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = stdout + ("\n" + stderr if stderr else "")
        return combined.strip()
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        combined = (out + ("\n" + err if err else "")).strip()
        return (combined + f"\n[Isolation probe timed out after {timeout_seconds}s]").strip()
    except (FileNotFoundError, OSError) as exc:
        return f"[Isolation probe failed to execute: {exc}]"


def analyse(
    output_lines: list[str] | str,
    exit_code: int | None,
    termination_reason: str | None,
    config: Any,
    probe_runner: Callable[..., Any] | None = None,
) -> FailureDiagnostic:
    """Analyse verification output and produce a FailureDiagnostic.

    Classifies the failure into HANG, ENV, CASCADE, or FLAKY in strict priority order.
    Extracts top error fingerprints, identifies the root failing test, bounds the
    log tail to at most 100 lines, and runs an isolation probe for candidate tests.
    """
    if isinstance(output_lines, str):
        lines = [line.rstrip("\r\n") for line in output_lines.splitlines()]
    else:
        lines = [str(line).rstrip("\r\n") for line in output_lines]

    # Bound log_tail to at most 100 lines
    log_tail = lines[-100:] if len(lines) > 100 else list(lines)

    # Extract test identifiers and error fingerprints
    test_ids = extract_test_identifiers(lines)
    root_tests = [test_ids[0]] if test_ids else []
    top_errors = extract_error_fingerprints(lines)

    # Determine first test identifier line index
    first_test_line_idx: int | None = None
    if root_tests:
        first_test = root_tests[0]
        for idx, line in enumerate(lines):
            if first_test in line:
                first_test_line_idx = idx
                break

    # 1. HANG: termination_reason is HANG / STALLED
    if termination_reason is not None and str(termination_reason).strip().upper() in {
        "HANG",
        "STALLED",
    }:
        label = LABEL_HANG
    # 2. ENV: setup/import errors appearing before the first test identifier line
    elif _check_env_failure(lines, first_test_line_idx):
        label = LABEL_ENV
    # 3. CASCADE: 5+ failures with a repeating error class
    elif _check_cascade_failure(lines, top_errors):
        label = LABEL_CASCADE
    # 4. FLAKY: fallback
    else:
        label = LABEL_FLAKY

    suggested_action = SUGGESTED_ACTIONS.get(
        label,
        SUGGESTED_ACTIONS[LABEL_FLAKY],
    )

    # Isolation rerun
    isolation_output: str | None = None
    # Isolation is only executed when a root test is identified and failure is CASCADE or FLAKY
    if label in (LABEL_CASCADE, LABEL_FLAKY) and root_tests:
        if isinstance(config, dict):
            test_cmd = config.get("test_cmd", "")
            isolation_cmd = config.get("isolation_cmd", "")
            timeout_seconds = config.get("timeout_seconds", 300)
        else:
            test_cmd = getattr(config, "test_cmd", "")
            isolation_cmd = getattr(config, "isolation_cmd", "")
            timeout_seconds = getattr(config, "timeout_seconds", 300)

        template = build_isolation_command(test_cmd, isolation_cmd)
        if template:
            argv = interpolate_isolation_command(template, test_id=root_tests[0])
            if argv:
                isolation_output = _run_isolation_probe(
                    argv,
                    timeout_seconds=timeout_seconds,
                    probe_runner=probe_runner,
                )

    return FailureDiagnostic(
        label=label,
        root_tests=root_tests,
        top_errors=top_errors,
        log_tail=log_tail,
        isolation_output=isolation_output,
        suggested_action=suggested_action,
    )


def render_diagnostic_report(
    diagnostic: FailureDiagnostic,
    token_count: int | str = 0,
    token_budget: int | str = 150000,
    prompt_question: bool = True,
) -> str:
    """Render a structured diagnostic report from FailureDiagnostic and token usage (T066).

    Format:
        ⚠ <LABEL> detected — <root_test or "unknown">
        Top errors: <top_errors joined by ", ">
        <isolation_output if present, else omitted>
        --- last 100 lines ---
        <log_tail>
        Token budget: <token_count> / <token_budget>
        Suggested: <suggested_action>
        Run /diagnosing-bugs? [Y/n]
    """
    root_test = diagnostic.root_tests[0] if diagnostic.root_tests else "unknown"
    label = diagnostic.label or LABEL_FLAKY
    top_errors_str = ", ".join(diagnostic.top_errors) if diagnostic.top_errors else "none"

    lines: list[str] = [
        f"⚠ {label} detected — {root_test}",
        f"Top errors: {top_errors_str}",
    ]

    if diagnostic.isolation_output and diagnostic.isolation_output.strip():
        lines.append(diagnostic.isolation_output.strip())

    lines.append("--- last 100 lines ---")

    bounded_tail = (
        diagnostic.log_tail[-100:]
        if len(diagnostic.log_tail) > 100
        else diagnostic.log_tail
    )
    if bounded_tail:
        lines.extend(bounded_tail)

    tc_str = f"{token_count:,}" if isinstance(token_count, int) else str(token_count)
    tb_str = f"{token_budget:,}" if isinstance(token_budget, int) else str(token_budget)
    lines.append(f"Token budget: {tc_str} / {tb_str}")

    suggested = (
        diagnostic.suggested_action
        or SUGGESTED_ACTIONS.get(label, SUGGESTED_ACTIONS[LABEL_FLAKY])
    )
    lines.append(f"Suggested: {suggested}")

    if prompt_question:
        lines.append("Run /diagnosing-bugs? [Y/n]")

    return "\n".join(lines)
