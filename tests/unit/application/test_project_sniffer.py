"""Unit tests for ProjectSniffer application service."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import pytest

from runner.application.scaffolding import ProjectSniffer
from runner.domain.scaffolding import ProjectHeuristics


def test_sniffer_detects_python_with_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "my-py-pkg"\n', encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert isinstance(heuristics, ProjectHeuristics)
    assert heuristics.detected_stack == "python"
    assert heuristics.test_cmd == "python -m pytest"
    assert heuristics.build_cmd == ""
    assert heuristics.base_branch == "main"
    assert heuristics.branch == "agent/ticket-runner"
    assert heuristics.provider == "opencode"
    assert heuristics.name in ("my-py-pkg", tmp_path.name)


def test_sniffer_detects_python_with_setup_py(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='test')\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "python"
    assert heuristics.test_cmd == "python -m pytest"


def test_sniffer_detects_python_with_requirements_txt(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest>=7.0\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "python"
    assert heuristics.test_cmd == "python -m pytest"


def test_sniffer_detects_node_npm_default(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "my-app", "scripts": {"test": "jest", "build": "tsc"}}', encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "node"
    assert heuristics.test_cmd == "npm test"
    assert heuristics.build_cmd == "npm run build"


def test_sniffer_detects_node_pnpm(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest", "build": "vite build"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 5.4\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "node"
    assert heuristics.test_cmd == "pnpm test"
    assert heuristics.build_cmd == "pnpm run build"


def test_sniffer_detects_node_yarn(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest", "build": "webpack"}}', encoding="utf-8")
    (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "node"
    assert heuristics.test_cmd == "yarn test"
    assert heuristics.build_cmd in ("yarn build", "yarn run build")


def test_sniffer_detects_node_bun(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {"test": "bun test", "build": "bun build ./src/index.ts"}}', encoding="utf-8")
    (tmp_path / "bun.lockb").write_text("binary-lockfile", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "node"
    assert heuristics.test_cmd == "bun test"
    assert heuristics.build_cmd == "bun run build"


def test_sniffer_handles_malformed_package_json(tmp_path: Path) -> None:
    # Malformed JSON should not crash sniffer, should still recognize node
    (tmp_path / "package.json").write_text('{"name": "broken", invalid json...', encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "node"
    assert heuristics.test_cmd == "npm test"
    assert heuristics.build_cmd == ""


def test_sniffer_detects_rust_cargo(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "my_crate"\nversion = "0.1.0"\n', encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "rust"
    assert heuristics.test_cmd == "cargo test"
    assert heuristics.build_cmd == "cargo build"


def test_sniffer_detects_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module github.com/example/demo\n\ngo 1.21\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "go"
    assert heuristics.test_cmd == "go test ./..."
    assert heuristics.build_cmd == ""


def test_sniffer_unknown_stack(tmp_path: Path) -> None:
    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.detected_stack == "unknown"
    assert heuristics.test_cmd == ""
    assert heuristics.build_cmd == ""
    assert heuristics.name == tmp_path.name


def test_sniffer_git_branch_detection_master(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.base_branch == "master"


def test_sniffer_git_branch_detection_main(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    assert heuristics.base_branch == "main"


def test_sniffer_git_detached_head_or_empty(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("1234567890abcdef1234567890abcdef12345678\n", encoding="utf-8")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(tmp_path)

    # Detached head cleanly falls back to "main"
    assert heuristics.base_branch == "main"


def test_sniffer_security_external_symlink_ignored(tmp_path: Path) -> None:
    external_dir = tmp_path / "outside"
    external_dir.mkdir()
    target_project = tmp_path / "project"
    target_project.mkdir()

    external_file = external_dir / "pyproject.toml"
    external_file.write_text('[project]\nname = "secret"\n', encoding="utf-8")

    # Create symlink pointing outside target_project
    symlink_file = target_project / "pyproject.toml"
    try:
        symlink_file.symlink_to(external_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform/user without privileges")

    sniffer = ProjectSniffer()
    heuristics = sniffer.sniff(target_project)

    # The external symlink must be ignored for security
    assert heuristics.detected_stack == "unknown"
