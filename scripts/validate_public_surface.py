#!/usr/bin/env python3
"""Fail CI if public entry points contain TODO / NotImplemented stubs."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PUBLIC_MODULES = [
    PROJECT_ROOT / "src" / "plinth" / "registry.py",
    PROJECT_ROOT / "src" / "plinth" / "config.py",
    PROJECT_ROOT / "src" / "plinth" / "rows.py",
    PROJECT_ROOT / "src" / "plinth" / "base_stage.py",
    PROJECT_ROOT / "src" / "plinth" / "testing" / "__init__.py",
]

FORBIDDEN = re.compile(r"\b(TODO|NotImplementedError|not yet implemented)\b", re.IGNORECASE)


def main() -> int:
    errors: list[str] = []
    for path in PUBLIC_MODULES:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            if line.strip().startswith("raise NotImplementedError"):
                continue
            if FORBIDDEN.search(line):
                errors.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}: {line.strip()}")
    if errors:
        print("Public surface TODO/stub gate failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Public surface has no TODO/stub markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
