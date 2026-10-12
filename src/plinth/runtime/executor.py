"""Engine-owned typical stage lifecycle execution."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from plinth.context import StageContext
from plinth.dataset.structures import DatasetManifest
from plinth.runtime.hashing import compute_directory_hash, compute_params_hash
from plinth.runtime.intent_conformance import verify_output_intent_conformance
from plinth.runtime.ledger_writer import LedgerWriter
from plinth.runtime.manifest_policy import should_replace_manifest
from plinth.runtime.row_count_guard import assert_no_silent_row_loss

logger = logging.getLogger(__name__)


class TypicalStageExecutor:
    def run(self, stage: Any, context: StageContext, *, arming_hash: str = "") -> Path:
        stage.prepare_context(context)
        stage._start_time = time.time()
        stage._context = context

        input_dir = context.get_input_dir()
        output_dir = context.get_output_dir()
        manifest = context.get_manifest()
        schema = context.get_schema()
        intent = stage.get_intent()

        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Executing stage: {stage.stage_name}")
        logger.info(f"  Input:  {input_dir}")
        logger.info(f"  Output: {output_dir}")

        if intent.required_input_columns:
            if manifest is None:
                raise ValueError(
                    f"Stage {stage.stage_name} requires a manifest "
                    f"(StageIntent.required_input_columns; author contract §StageIntent): "
                    "no manifest available at input"
                )
            missing = intent.required_input_columns - set(manifest.df.columns)
            if missing:
                raise ValueError(
                    f"Stage {stage.stage_name} requires input columns {missing} "
                    f"(StageIntent.required_input_columns; author contract §StageIntent): "
                    f"columns missing from manifest"
                )

        ledger = context.get_ledger()
        if ledger.entries:
            logger.info(f"  Previous stages: {' → '.join(ledger.get_stage_history())}")

        output_manifest = DatasetManifest(manifest.df.copy(), schema=schema) if manifest else None

        try:
            stage._process_all_files(input_dir, output_dir, output_manifest)
        except Exception as e:
            logger.error(f"Error processing files in {stage.stage_name}: {e}")
            raise

        for col, dtype in intent.write_columns.items():
            schema.columns[col] = dtype

        if intent.append_to_unique_key:
            for col in intent.append_to_unique_key:
                if col not in schema.unique_key:
                    schema.unique_key.append(col)
                    logger.info(f"  Appending '{col}' to schema unique_key: {schema.unique_key}")

        if output_manifest and intent.write_columns:
            missing_outputs = set(intent.write_columns.keys()) - set(output_manifest.df.columns)
            if missing_outputs and len(output_manifest) > 0:
                raise ValueError(
                    f"Stage {stage.stage_name} declared output columns {missing_outputs} "
                    f"(StageIntent.write_columns; author contract §StageIntent) "
                    f"but did not produce them"
                )

        verify_output_intent_conformance(
            stage,
            intent,
            manifest,
            output_manifest,
            output_dir,
        )

        input_row_count = len(manifest) if manifest is not None else 0
        output_row_count = len(output_manifest) if output_manifest is not None else 0
        assert_no_silent_row_loss(
            stage.stage_name,
            intent,
            input_row_count,
            output_row_count,
        )

        context.save_schema(schema)

        if output_manifest is not None:
            replace = should_replace_manifest(intent)
            if not replace and not output_manifest.has_unique_rows():
                # Rows were updated in place by position; a key-aligned merge would cross-join duplicates.
                logger.warning(f"  Unique key does not identify rows uniquely; replacing manifest ({stage.stage_name})")
                replace = True
            context.update_manifest(output_manifest, replace=replace)
            if replace:
                logger.info(f"Replaced manifest with {len(output_manifest)} entries")
            else:
                logger.info(f"Saved updated manifest with {len(output_manifest)} entries")

        input_hash = compute_directory_hash(input_dir)
        output_hash = compute_directory_hash(output_dir)
        params_hash = compute_params_hash(stage.config)
        ledger_params = dict(stage.config)
        dropped_rows = getattr(stage, "_dropped_rows", 0)
        if dropped_rows > 0:
            ledger_params["dropped_rows"] = dropped_rows

        duration = time.time() - (stage._start_time or time.time())
        LedgerWriter().append_entry(
            ledger,
            stage_name=stage.stage_name,
            function_name=stage.__class__.__name__,
            input_directory=str(input_dir),
            output_directory=str(output_dir),
            input_hash=input_hash,
            output_hash=output_hash,
            params_hash=params_hash,
            arming_hash=arming_hash,
            params=ledger_params,
            files_processed=stage._files_processed,
            duration_seconds=duration,
        )
        LedgerWriter().write(ledger, output_dir)

        logger.info(f"✓ {stage.stage_name} completed: {stage._files_processed} items in {duration:.2f}s")
        logger.info(f"  Pipeline version: {ledger.get_pipeline_version()}")

        return Path(stage.finalize_output(context, output_dir))
