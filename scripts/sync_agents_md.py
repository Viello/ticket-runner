"""One-way upstream-to-sandbox drift detector and synchronizer for AGENTS.md."""

from __future__ import annotations

import argparse
import datetime
import difflib
from pathlib import Path
import sys

from runner.tools.scaffold_sandbox import (
    DEFAULT_PREAMBLE,
    extract_curated_subset,
    format_sandbox_agents_md,
    get_default_target_dir,
    parse_sandbox_agents_md,
)


def _resolve_default_upstream() -> Path:
    """Resolve default upstream AGENTS.md path."""
    candidates = [
        Path(__file__).resolve().parents[1] / "AGENTS.md",
        Path(r"D:\Projects\AGENTS.md"),
        Path.cwd() / "AGENTS.md",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


def sync_agents_md(
    target_dir: Path,
    upstream_path: Path | None = None,
    *,
    write: bool = False,
) -> int:
    """Compare sandbox AGENTS.md curated subset against upstream.

    Args:
        target_dir: Directory containing sandbox AGENTS.md.
        upstream_path: Optional path to upstream AGENTS.md.
        write: If True, overwrite sandbox copy with updated upstream subset and fresh sync stamp.

    Returns:
        0 if in sync (or successfully written), 1 if drift detected, 2 on missing-file I/O.
    """
    upstream = (upstream_path or _resolve_default_upstream()).resolve()
    target_path = (target_dir / "AGENTS.md" if target_dir.is_dir() else target_dir).resolve()

    if not upstream.is_file():
        print(f"Error: Upstream AGENTS.md not found at '{upstream}'", file=sys.stderr)
        return 2

    if not target_path.is_file():
        print(f"Error: Sandbox AGENTS.md not found at '{target_path}'", file=sys.stderr)
        return 2

    try:
        upstream_text = upstream.read_text(encoding="utf-8")
        sandbox_text = target_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading file: {exc}", file=sys.stderr)
        return 2

    upstream_curated = extract_curated_subset(upstream_text)
    preamble, stamp_date, sandbox_curated = parse_sandbox_agents_md(sandbox_text)

    if not preamble.strip():
        preamble = DEFAULT_PREAMBLE

    if upstream_curated.strip() == sandbox_curated.strip():
        print(f"Sandbox AGENTS.md at '{target_path}' is in sync with upstream '{upstream}'.")
        return 0

    if write:
        today = datetime.date.today().isoformat()
        new_content = format_sandbox_agents_md(preamble, today, upstream_curated)
        try:
            target_path.write_text(new_content, encoding="utf-8")
            print(f"Updated '{target_path}' with upstream curated subset (stamp date: {today}).")
            return 0
        except OSError as exc:
            print(f"Error writing to '{target_path}': {exc}", file=sys.stderr)
            return 2

    # Drift detected
    diff = list(
        difflib.unified_diff(
            sandbox_curated.strip().splitlines(keepends=True),
            upstream_curated.strip().splitlines(keepends=True),
            fromfile=f"sandbox/{target_path.name}",
            tofile=f"upstream/{upstream.name}",
        )
    )
    sys.stdout.writelines(diff)
    print(
        f"\nDrift detected between '{upstream}' and '{target_path}'. Run with --write to sync.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for AGENTS.md sync detector."""
    parser = argparse.ArgumentParser(
        prog="scripts.sync_agents_md",
        description="One-way drift detector and synchronizer for sandbox AGENTS.md.",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=get_default_target_dir(),
        help="Path to sandbox directory containing AGENTS.md",
    )
    parser.add_argument(
        "--upstream",
        type=Path,
        default=None,
        help="Optional path to upstream AGENTS.md",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply upstream changes to sandbox copy with a fresh sync stamp",
    )

    args = parser.parse_args(argv)
    return sync_agents_md(args.target_dir, args.upstream, write=args.write)


if __name__ == "__main__":
    sys.exit(main())
