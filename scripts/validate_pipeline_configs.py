#!/usr/bin/env python3
"""Validate committed pipeline YAML against published JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "docs" / "schemas" / "pipeline_config.schema.json"
CONFIG_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "golden_pipeline"


def _format_path(prefix: str, path: list[str | int]) -> str:
    parts = [prefix]
    for segment in path:
        if isinstance(segment, int):
            parts[-1] = f"{parts[-1]}[{segment}]"
        else:
            parts.append(str(segment))
    return ".".join(parts)


def _load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Missing schema: {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _discover_yaml_paths() -> list[Path]:
    paths: list[Path] = []
    root_config = CONFIG_ROOT / "config.yaml"
    if root_config.exists():
        paths.append(root_config)
    tiers_dir = CONFIG_ROOT / "tiers"
    if tiers_dir.exists():
        paths.extend(sorted(tiers_dir.glob("*/config.yaml")))
    return paths


def _validate_instance(instance: dict, schema: dict, path: list[str | int]) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema package required for pipeline config validation"]

    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        location = _format_path("config", list(error.absolute_path))
        errors.append(f"{location}: {error.message}")
    return errors


def validate_file(path: Path, schema: dict) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return [f"{path}: root must be a mapping"]
    rel = path.relative_to(PROJECT_ROOT)
    prefixed = _validate_instance(data, schema, [])
    return [f"{rel}: {err}" if not err.startswith("config") else f"{rel}: {err}" for err in prefixed]


def main() -> int:
    schema = _load_schema()
    yaml_paths = _discover_yaml_paths()
    if not yaml_paths:
        print("No pipeline YAML files discovered under tests/fixtures/golden_pipeline/")
        return 1

    all_errors: list[str] = []
    for path in yaml_paths:
        all_errors.extend(validate_file(path, schema))

    if all_errors:
        print("Pipeline config validation failed:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"Pipeline config validation passed ({len(yaml_paths)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
