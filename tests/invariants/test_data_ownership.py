"""Data ownership contract tests."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_ROOT = PROJECT_ROOT / "src" / "plinth"
DESIGNATED_LEDGER_WRITER = SRC_ROOT / "runtime" / "ledger_writer.py"


def _python_files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _find_metadata_ledger_write_sites(path: Path) -> list[int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    hits: list[int] = []
    for lineno, line in enumerate(lines, start=1):
        if "metadata_ledger.yaml" in line and ".to_yaml(" in line.replace(" ", ""):
            hits.append(lineno)
        if "metadata_ledger.yaml" in line and "write_text" in line:
            hits.append(lineno)
    return hits


def test_metadata_ledger_disk_writes_only_in_ledger_writer() -> None:
    offenders: list[str] = []
    for path in _python_files_under(SRC_ROOT):
        if path == DESIGNATED_LEDGER_WRITER:
            continue
        for lineno in _find_metadata_ledger_write_sites(path):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}")
    assert offenders == [], f"Ledger writes outside LedgerWriter: {offenders}"


def test_ledger_writer_is_designated_component() -> None:
    assert DESIGNATED_LEDGER_WRITER.exists()
    content = DESIGNATED_LEDGER_WRITER.read_text(encoding="utf-8")
    assert "metadata_ledger.yaml" in content
    assert "class LedgerWriter" in content
