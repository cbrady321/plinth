"""Closed StageOutcome author surface on base_stage."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_base_stage_outcome_surface_ast_scan() -> None:
    script = PROJECT_ROOT / "scripts" / "validate_stage_outcome_surface.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_base_stage_mypy_clean() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "src/plinth/base_stage.py", "--follow-imports=skip"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
