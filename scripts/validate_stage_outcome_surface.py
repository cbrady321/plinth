#!/usr/bin/env python3
"""Validate closed StageOutcome author surface on base_stage."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_STAGE_PATH = PROJECT_ROOT / "src" / "plinth" / "base_stage.py"
AUTHOR_METHODS = frozenset({"process_file", "process_group"})


def _annotation_contains_dict(node: ast.expr | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id == "Dict"
    if isinstance(node, ast.Subscript):
        value = node.value
        if isinstance(value, ast.Name) and value.id == "Dict":
            return True
        if isinstance(value, ast.Attribute) and value.attr == "Dict":
            return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation_contains_dict(node.left) or _annotation_contains_dict(
            node.right
        )
    if isinstance(node, ast.Tuple):
        return any(_annotation_contains_dict(elt) for elt in node.elts)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id == "Union":
            slice_node = node.slice
            if isinstance(slice_node, ast.Tuple):
                return any(_annotation_contains_dict(elt) for elt in slice_node.elts)
    return False


def _validate_base_stage(source: str) -> list[str]:
    tree = ast.parse(source)
    errors: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in AUTHOR_METHODS:
            continue
        if _annotation_contains_dict(node.returns):
            errors.append(
                f"{node.name} return annotation must be StageOutcome only "
                f"(found a Dict/Union return annotation at line {node.lineno})"
            )
        elif node.returns is None:
            errors.append(f"{node.name} missing return annotation (line {node.lineno})")
        elif isinstance(node.returns, ast.Name) and node.returns.id != "StageOutcome":
            errors.append(
                f"{node.name} return annotation must be StageOutcome "
                f"(found {node.returns.id} at line {node.lineno})"
            )

    return errors


def main() -> int:
    if not BASE_STAGE_PATH.exists():
        print(f"Missing base stage module: {BASE_STAGE_PATH}", file=sys.stderr)
        return 1

    errors = _validate_base_stage(BASE_STAGE_PATH.read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("StageOutcome surface OK on base_stage.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
