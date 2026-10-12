#!/usr/bin/env python3
"""Validate expectation matrix rows link to existing positive and negative tests."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PROJECT_ROOT / "docs" / "expectation_matrix.md"

ROW_ID_RE = re.compile(r"^E\d+$")
TEST_FUNC_RE = re.compile(r"^def (test_[\w]+)")

# Rows that share one module but need explicit allowlist (e.g. single-function API surface).
SAME_FILE_ALLOWLIST = frozenset()


def _parse_table_rows(text: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5:
            continue
        row_id = cells[0]
        if not ROW_ID_RE.match(row_id):
            continue
        positive_cell = cells[3]
        negative_cell = cells[4]
        rows.append((row_id, positive_cell, negative_cell))
    return rows


def _collect_test_paths(cell: str) -> list[Path]:
    paths: list[Path] = []
    for token in cell.split():
        if token.startswith("tests/") and token.endswith(".py"):
            paths.append(PROJECT_ROOT / token)
    return paths


def _test_functions_in_file(path: Path) -> set[str]:
    names: set[str] = set()
    if not path.exists():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TEST_FUNC_RE.match(line)
        if match:
            names.add(match.group(1))
    return names


def _validate_matrix(check_scenarios: bool) -> list[str]:
    errors: list[str] = []
    if not MATRIX_PATH.exists():
        return [f"Missing expectation matrix: {MATRIX_PATH}"]

    rows = _parse_table_rows(MATRIX_PATH.read_text(encoding="utf-8"))
    if not rows:
        errors.append("No expectation rows parsed from matrix table")
    elif len(rows) < 52:
        errors.append(f"Expected ≥52 expectation rows, found {len(rows)}")

    for row_id, positive_cell, negative_cell in rows:
        positive_paths = _collect_test_paths(positive_cell)
        negative_paths = _collect_test_paths(negative_cell)

        if not positive_paths:
            errors.append(f"{row_id}: no positive test path in '{positive_cell}'")
        if not negative_paths:
            errors.append(f"{row_id}: no negative test path in '{negative_cell}'")

        pos_set = {p.resolve() for p in positive_paths}
        neg_set = {p.resolve() for p in negative_paths}

        for path in positive_paths + negative_paths:
            if not path.exists():
                errors.append(f"{row_id}: missing test file {path.relative_to(PROJECT_ROOT)}")

        overlap = pos_set & neg_set
        if overlap:
            if row_id in SAME_FILE_ALLOWLIST:
                pass
            else:
                shared = overlap.pop()
                funcs = _test_functions_in_file(shared)
                if len(funcs) < 2:
                    rel = shared.relative_to(PROJECT_ROOT).as_posix()
                    errors.append(
                        f"{row_id}: positive and negative share {rel} with <2 test functions"
                    )
                elif check_scenarios:
                    print(
                        f"  note: {row_id} uses distinct scenarios in "
                        f"{shared.relative_to(PROJECT_ROOT).as_posix()} ({len(funcs)} tests)"
                    )

        if check_scenarios and positive_paths and negative_paths and not (pos_set & neg_set):
            pos_funcs = _test_functions_in_file(positive_paths[0])
            neg_funcs = _test_functions_in_file(negative_paths[0])
            if not pos_funcs or not neg_funcs:
                errors.append(f"{row_id}: could not parse test functions for scenario check")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-scenarios", action="store_true")
    args = parser.parse_args()

    errors = _validate_matrix(check_scenarios=args.check_scenarios)
    if errors:
        print("Expectation matrix validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    row_count = len(_parse_table_rows(MATRIX_PATH.read_text(encoding="utf-8")))
    print(f"Expectation matrix: {row_count} rows validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
