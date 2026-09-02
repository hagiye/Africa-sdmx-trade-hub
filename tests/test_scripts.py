"""Tests for command-line script entry points."""

import runpy
from pathlib import Path


def test_database_script_imports_when_run_by_path() -> None:
    """The documented ``python scripts/...`` form can import the app package."""
    script = Path(__file__).parents[1] / "scripts" / "test_database.py"

    namespace = runpy.run_path(str(script), run_name="test_database_script")

    assert callable(namespace["main"])
