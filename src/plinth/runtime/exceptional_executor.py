"""Exceptional stage execution wrapper."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from plinth.context import StageContext
from plinth.dataset.structures import MetadataLedger
from plinth.registry import ExceptionalMetadata, StageRegistry
from plinth.runtime.exceptional_obligation_verifier import verify_exceptional_obligations
from plinth.runtime.ledger_writer import LedgerWriter

logger = logging.getLogger(__name__)


class ExceptionalStageExecutor:
    def run(self, stage: Any, context: StageContext, *, arming_hash: str = "") -> Path:
        prepare = getattr(stage, "prepare_context", None)
        if callable(prepare):
            prepare(context)

        input_ledger_entries = len(context.get_ledger().entries)

        input_manifest = context.get_manifest()
        input_row_count = len(input_manifest) if input_manifest is not None else 0

        logger.info(f"Executing exceptional stage: {stage.stage_name}")
        result = stage.execute(context)
        output_dir = Path(result) if result is not None else context.get_output_dir()

        output_manifest = context.get_manifest()
        output_row_count = len(output_manifest) if output_manifest is not None else 0
        from plinth.runtime.row_count_guard import assert_no_silent_row_loss

        assert_no_silent_row_loss(
            stage.stage_name,
            stage.get_intent(),
            input_row_count,
            output_row_count,
        )

        verify_exceptional_obligations(
            stage.stage_name,
            context,
            input_ledger_entries=input_ledger_entries,
        )

        metadata = StageRegistry.get_exceptional_metadata(stage.stage_name) or ExceptionalMetadata()
        if metadata.obligations.records_ledger:
            ledger = MetadataLedger.from_directory(output_dir)
            if ledger.entries and ledger.entries[-1].arming_hash != arming_hash:
                ledger.entries[-1].arming_hash = arming_hash
                LedgerWriter().write(ledger, output_dir)

        finalize = getattr(stage, "finalize_output", None)
        if callable(finalize):
            return Path(finalize(context, output_dir))

        return output_dir
