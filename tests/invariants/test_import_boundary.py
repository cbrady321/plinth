"""Import boundary contract tests."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_importlinter_contract_file_exists() -> None:
    config = PROJECT_ROOT / ".importlinter"
    assert config.exists()
    text = config.read_text(encoding="utf-8")
    assert "plinth" in text
    assert "forbidden" in text
    assert "blocks-no-executors" in text
    assert "pipeline-orchestration-only" in text
    assert "runtime-layering" in text
    assert "library-domain-free" in text
    assert "plinth.runtime.executor" in text
