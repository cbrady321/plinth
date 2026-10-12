"""Golden tier tests register fixture-only stages."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_golden_stages() -> None:
    path = Path(__file__).resolve().parent / "golden_stages.py"
    spec = importlib.util.spec_from_file_location("golden_stages", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


@pytest.fixture(scope="session", autouse=True)
def _register_golden_stages() -> None:
    _load_golden_stages()
