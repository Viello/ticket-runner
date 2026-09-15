"""Root pytest configuration and shared fixtures."""

from pathlib import Path
import pytest


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary directory Path."""
    return tmp_path
