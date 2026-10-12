"""Stable test harness imports and helpers for stage authors."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.context import FileSystemStageContext, InMemoryStageContext, StageContext
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.runtime.executor import TypicalStageExecutor

__all__ = [
    "FileSystemStageContext",
    "InMemoryStageContext",
    "StageContext",
    "TypicalStageExecutor",
    "minimal_manifest",
    "run_typical_stage",
    "assert_manifest_has_columns",
]


def minimal_manifest(
    rows: list[dict[str, Any]],
    schema: Optional[DatasetSchema] = None,
) -> DatasetManifest:
    """Build a manifest from row dicts using the default or supplied schema."""
    schema = schema or DatasetSchema()
    return DatasetManifest(pd.DataFrame(rows), schema=schema)


def run_typical_stage(
    stage: BaseStage,
    rows: list[dict[str, Any]],
    schema: Optional[DatasetSchema] = None,
) -> InMemoryStageContext:
    """Run a typical stage in memory and return the resulting context."""
    manifest = minimal_manifest(rows, schema=schema)
    context = InMemoryStageContext(manifest=manifest, schema=schema or DatasetSchema())
    TypicalStageExecutor().run(stage, context)
    return context


def assert_manifest_has_columns(manifest: DatasetManifest, required: set[str]) -> None:
    """Raise AssertionError when required columns are missing from a manifest."""
    present = set(manifest.df.columns)
    missing = required - present
    if missing:
        raise AssertionError(f"Manifest missing columns: {sorted(missing)}")
