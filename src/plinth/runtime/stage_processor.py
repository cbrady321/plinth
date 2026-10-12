"""Engine-owned manifest iteration and file processing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from tqdm import tqdm

from plinth.dataset.manifest_paths import manifest_csv_path
from plinth.dataset.media import NO_SOURCE_FILE, SOURCE_PATH_KEY, MediaSpec
from plinth.dataset.structures import DatasetManifest, DatasetSchema, MetadataLedger
from plinth.intent import StageIntent
from plinth.runtime.outcome_handler import OutcomeHandler
from plinth.runtime.propagation_engine import PropagationEngine
from plinth.runtime.row_failure_policy import RowFailurePolicy

logger = logging.getLogger(__name__)


class StageFileProcessor:
    def process(
        self,
        stage: Any,
        input_dir: Path,
        output_dir: Path,
        manifest: Optional[DatasetManifest],
    ) -> None:
        if manifest is None:
            manifest = self._load_manifest_from_input(input_dir)

        if manifest is None or len(manifest) == 0:
            logger.warning(f"No manifest found or manifest is empty in {input_dir}")
            return

        logger.info(f"Processing {len(manifest)} rows from manifest CSV")
        intent = stage.get_intent()
        row_policy = RowFailurePolicy(stage, intent)
        is_structural_change = self._is_structural_change(intent)
        new_rows: Optional[list[dict[str, Any]]] = [] if is_structural_change else None
        outcome_handler = OutcomeHandler(
            stage.stage_name, runtime_keys=frozenset({SOURCE_PATH_KEY}) - set(manifest.df.columns)
        )
        propagator = PropagationEngine()
        media = self._resolve_media(stage, input_dir)

        if intent.group_by:
            self._process_groups(
                stage,
                manifest,
                intent.group_by,
                input_dir,
                output_dir,
                new_rows if new_rows is not None else [],
                outcome_handler,
                row_policy,
            )
        else:
            self._process_single_rows(
                stage,
                manifest,
                input_dir,
                output_dir,
                intent,
                is_structural_change,
                new_rows,
                outcome_handler,
                propagator,
                row_policy,
                media,
            )

        row_policy.finalize()

        if is_structural_change and new_rows is not None:
            manifest.df = pd.DataFrame(new_rows)
            logger.info(f"Rebuilt manifest with {len(manifest)} rows")

    @staticmethod
    def _resolve_media(stage: Any, input_dir: Path) -> MediaSpec:
        context = getattr(stage, "_context", None)
        if context is not None:
            media: MediaSpec = context.get_schema().media
            return media
        return DatasetSchema.for_directory(input_dir).media

    @staticmethod
    def _is_structural_change(intent: StageIntent) -> bool:
        return bool(intent.filters_rows or intent.expands_rows or intent.aggregates_rows or intent.group_by is not None)

    def _process_groups(
        self,
        stage: Any,
        manifest: DatasetManifest,
        group_cols: list[str],
        input_dir: Path,
        output_dir: Path,
        new_rows: list[dict[str, Any]],
        outcome_handler: OutcomeHandler,
        row_policy: RowFailurePolicy,
    ) -> None:
        grouped = manifest.df.groupby(group_cols)
        logger.info(f"Processing {len(grouped)} groups (grouped by {group_cols})")

        progress = tqdm(grouped, desc=f"Processing groups ({stage.stage_name})", disable=None)
        for group_index, (name, group) in enumerate(progress):
            try:
                if isinstance(name, tuple):
                    keys = dict(zip(group_cols, name))
                else:
                    keys = {group_cols[0]: name}
                rows = group.to_dict("records")
                result = stage.process_group(keys, rows, input_dir, output_dir)
                outcome_handler.handle_result(result, None, new_rows, True)

                stage._files_processed += 1
                if stage._files_processed % 10 == 0:
                    logger.info(f"  Processed {stage._files_processed} groups...")
            except Exception as e:
                if isinstance(e, ValueError) and ("failed at row" in str(e) or "dropped" in str(e)):
                    raise
                if isinstance(e, (ImportError, ModuleNotFoundError, TypeError)):
                    raise
                row_policy.record_failure(group_index, str(e))

    def _process_single_rows(
        self,
        stage: Any,
        manifest: DatasetManifest,
        input_dir: Path,
        output_dir: Path,
        intent: StageIntent,
        is_structural_change: bool,
        new_rows: Optional[list[dict[str, Any]]],
        outcome_handler: OutcomeHandler,
        propagator: PropagationEngine,
        row_policy: RowFailurePolicy,
        media: MediaSpec,
    ) -> None:
        always_propagate = bool(stage.config.get("_always_propagate", False))
        upstream_dirs = MetadataLedger.from_directory(input_dir).upstream_directories()
        # A manifest column of the same name is the dataset's own data: never overwrite it.
        inject_source_path = SOURCE_PATH_KEY not in manifest.df.columns

        for idx in tqdm(range(len(manifest)), desc=f"Processing rows ({stage.stage_name})", disable=None):
            try:
                row = manifest[idx]
                resolved = media.source_path(row, input_dir, upstream_dirs)

                if resolved is None and intent.reads_files:
                    row_policy.record_failure(idx, f"missing {media.path_column}")
                    continue

                if resolved is not None and intent.reads_files and not resolved.exists():
                    row_policy.record_failure(idx, f"input file not found: {resolved}")
                    continue

                source_path = resolved if resolved is not None else NO_SOURCE_FILE
                filename = media.file_name(row, resolved) if resolved is not None else f"row_{idx}"
                output_path = media.output_path(output_dir, filename)

                if intent.modifies_files:
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                metadata = dict(row)
                if inject_source_path:
                    metadata[SOURCE_PATH_KEY] = str(source_path)
                result = stage.process_file(source_path, output_path, metadata)
                outcome_handler.handle_result(result, row, new_rows, is_structural_change, manifest, row_index=idx)

                propagator.propagate_if_needed(
                    always_propagate=always_propagate and resolved is not None,
                    output_path=output_path,
                    source_path=source_path,
                    path_column=media.path_column,
                    filename=filename,
                    row=row,
                    is_structural_change=is_structural_change,
                    new_rows=new_rows,
                    manifest=manifest,
                    row_index=idx,
                )

                stage._files_processed += 1
                if stage._files_processed % 10 == 0:
                    logger.info(f"  Processed {stage._files_processed} files...")
            except Exception as e:
                if isinstance(e, ValueError) and ("failed at row" in str(e) or "dropped" in str(e)):
                    raise
                if isinstance(e, (ImportError, ModuleNotFoundError, TypeError)):
                    raise
                row_policy.record_failure(idx, str(e))

    @staticmethod
    def _load_manifest_from_input(input_dir: Path) -> Optional[DatasetManifest]:
        manifest_path = manifest_csv_path(input_dir)
        if manifest_path.exists():
            schema = DatasetSchema.for_directory(input_dir)
            return DatasetManifest.from_csv(manifest_path, schema=schema)
        return None
