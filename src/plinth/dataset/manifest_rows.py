"""Canonical, location-independent form of manifest rows (snapshots, resume checks, hashing)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetSchema


def _normalize_cell(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def normalize_manifest_row(row: dict[str, Any], media: MediaSpec = MediaSpec()) -> dict[str, Any]:
    """Sort keys, null-normalize cells and make the file-pointer column location-independent."""
    normalized = dict(sorted((key, _normalize_cell(value)) for key, value in row.items()))
    portable = media.portable_path(normalized)
    if portable is not None:
        normalized[media.path_column] = portable
    return normalized


def normalize_manifest_rows(manifest_path: Path) -> tuple[dict[str, Any], ...]:
    media = DatasetSchema.for_directory(manifest_path.parent).media
    dataframe = pd.read_csv(manifest_path)
    dataframe = dataframe.sort_values(by=list(dataframe.columns)).reset_index(drop=True)
    records = dataframe.to_dict(orient="records")
    return tuple(normalize_manifest_row({str(k): v for k, v in record.items()}, media) for record in records)
