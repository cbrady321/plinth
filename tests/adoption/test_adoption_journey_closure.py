"""Release documentation checks."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"


def test_plinth_version_matches_changelog() -> None:
    from plinth import __version__

    changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog
