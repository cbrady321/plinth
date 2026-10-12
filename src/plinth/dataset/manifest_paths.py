"""Canonical manifest artifact locations."""

from pathlib import Path

MANIFEST_CSV = "manifest.csv"
DATASET_SCHEMA_YAML = "dataset_schema.yaml"


def manifest_csv_path(directory: Path) -> Path:
    return directory / MANIFEST_CSV


def dataset_schema_path(directory: Path) -> Path:
    return directory / DATASET_SCHEMA_YAML
