#!/usr/bin/env python3
"""Verify ledger artifact writes occur only in LedgerWriter."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DESIGNATED = SRC_ROOT / "plinth" / "runtime" / "ledger_writer.py"


def _ledger_write_sites(path: Path) -> list[int]:
    hits: list[int] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if "metadata_ledger.yaml" in line and (".to_yaml(" in line or "write_text" in line):
            hits.append(lineno)
    return hits


def main() -> int:
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts or path == DESIGNATED:
            continue
        for lineno in _ledger_write_sites(path):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}")
    if offenders:
        print("Ledger write-site gate failed:")
        for item in offenders:
            print(f"  - {item}")
        return 1
    print("Ledger write-site gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
