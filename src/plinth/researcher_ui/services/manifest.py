"""Manifest and schema preview services."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from plinth.dataset.structures import DatasetSchema
from plinth.researcher_ui.models import ManifestPage, SchemaSummary
from plinth.researcher_ui.services.run_index import _schema_path, resolve_run_dir, resolve_stage_dir


def _identity_warning(df: pd.DataFrame, schema: DatasetSchema) -> str | None:
    key_cols = schema.effective_unique_key(set(df.columns))
    missing = [col for col in key_cols if col not in df.columns]
    if missing:
        return f"Missing required identity columns: {', '.join(missing)}"
    entity_col = schema.identity.entity_key if schema.identity else "entity_id"
    if entity_col not in df.columns and "entity_id" not in df.columns:
        return "Manifest is missing entity_id and declared identity key column"
    return None


def load_manifest_page(
    runs_dir: Path,
    run_id: str,
    stage_path: str,
    *,
    page: int = 1,
    page_size: int = 50,
    entity_id: str | None = None,
) -> ManifestPage:
    stage_dir = resolve_stage_dir(resolve_run_dir(runs_dir, run_id), stage_path)
    if stage_dir is None:
        return ManifestPage(
            stage_path=stage_path,
            columns=[],
            rows=[],
            page=page,
            page_size=page_size,
            total_rows=0,
            error=f"Stage path not found: {run_id}/{stage_path}",
        )

    manifest_path = stage_dir / "manifest.csv"
    if not manifest_path.exists():
        return ManifestPage(
            stage_path=stage_path,
            columns=[],
            rows=[],
            page=page,
            page_size=page_size,
            total_rows=0,
            error=f"Missing manifest.csv at {manifest_path}",
        )

    try:
        df = pd.read_csv(manifest_path)
    except Exception as exc:
        return ManifestPage(
            stage_path=stage_path,
            columns=[],
            rows=[],
            page=page,
            page_size=page_size,
            total_rows=0,
            error=f"Unreadable manifest.csv at {manifest_path}: {exc}",
        )

    schema_path = _schema_path(stage_dir)
    warning = None
    entity_col = "entity_id"
    if schema_path:
        try:
            schema = DatasetSchema.from_yaml(schema_path)
            warning = _identity_warning(df, schema)
            entity_col = schema.identity.entity_key if schema.identity else "entity_id"
        except Exception:
            warning = None

    if entity_id:
        filter_col = entity_col if entity_col in df.columns else "entity_id"
        if filter_col in df.columns:
            df = df[df[filter_col].astype(str) == str(entity_id)]
        else:
            return ManifestPage(
                stage_path=stage_path,
                columns=list(df.columns),
                rows=[],
                page=page,
                page_size=page_size,
                total_rows=0,
                entity_filter=entity_id,
                error=f"Cannot filter by entity_id — column {filter_col!r} not found in manifest",
            )

    page = max(1, page)
    page_size = min(max(1, page_size), 500)
    start = (page - 1) * page_size
    end = start + page_size
    slice_df = df.iloc[start:end]
    records = slice_df.astype(object).where(pd.notnull(slice_df), None).to_dict(orient="records")
    rows = [{str(key): value for key, value in record.items()} for record in records]
    total_rows = len(df)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)

    return ManifestPage(
        stage_path=stage_path,
        columns=list(df.columns),
        rows=rows,
        page=page,
        page_size=page_size,
        total_rows=total_rows,
        total_pages=total_pages,
        manifest_path=str(manifest_path),
        manifest_size_bytes=manifest_path.stat().st_size,
        identity_warning=warning,
        entity_filter=entity_id,
    )


def load_schema_summary(runs_dir: Path, run_id: str, stage_path: str) -> SchemaSummary:
    stage_dir = resolve_stage_dir(resolve_run_dir(runs_dir, run_id), stage_path)
    if stage_dir is None:
        return SchemaSummary(
            stage_path=stage_path,
            error=f"Stage path not found: {run_id}/{stage_path}",
        )

    schema_path = _schema_path(stage_dir)
    if schema_path is None:
        return SchemaSummary(
            stage_path=stage_path,
            error=f"Missing schema file (dataset_schema.yaml or schema.yaml) at {stage_dir}",
        )

    try:
        raw = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
        schema = DatasetSchema.from_dict(raw, source=schema_path)
    except Exception as exc:
        return SchemaSummary(
            stage_path=stage_path,
            schema_path=str(schema_path),
            error=f"Unreadable schema at {schema_path}: {exc}",
        )

    identity = {
        "entity_key": schema.identity.entity_key,
        "hierarchy_keys": list(schema.identity.hierarchy_keys),
        "disambiguator": schema.identity.disambiguator,
        "column_aliases": dict(schema.identity.column_aliases),
        "key_types": dict(schema.identity.key_types),
    }
    media = {
        "path_column": schema.media.path_column,
        "subdir": schema.media.subdir,
        "name_column": schema.media.name_column,
    }
    return SchemaSummary(
        stage_path=stage_path,
        unique_key=list(schema.unique_key),
        identity=identity,
        columns=dict(schema.columns),
        media=media,
        schema_path=str(schema_path),
    )
