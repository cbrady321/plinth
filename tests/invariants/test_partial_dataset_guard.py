"""Partial dataset guard tests."""

from __future__ import annotations

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.runtime.exceptional_executor import ExceptionalStageExecutor
from plinth.runtime.ledger_writer import LedgerWriter


def _manifest(rows: list[dict[str, object]]) -> DatasetManifest:
    return DatasetManifest(pd.DataFrame(rows))


def _base_row(entity_id: str = "s1", filename: str = "a.bin") -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "batch": 1,
        "slot": None,
        "filename": filename,
        "file_path": f"files/{filename}",
    }


class StubSilentRowDropStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path, output_path, metadata):
        raise NotImplementedError

    def execute(self, context: InMemoryStageContext) -> None:
        manifest = context.get_manifest()
        if manifest is None:
            raise ValueError("manifest required")
        trimmed = DatasetManifest(manifest.df.iloc[:1].copy())
        context.update_manifest(trimmed, replace=True)
        ledger = context.get_ledger()
        LedgerWriter().append_entry(
            ledger,
            stage_name=self.stage_name,
            function_name=self.__class__.__name__,
            input_directory=str(context.get_input_dir()),
            output_directory=str(context.get_output_dir()),
            input_hash="in",
            output_hash="out",
            params_hash="params",
            params={},
            files_processed=1,
            duration_seconds=0.0,
        )
        LedgerWriter().write(ledger, context.get_output_dir())
        return context.get_output_dir()


def test_exceptional_stage_cannot_silently_drop_rows(isolated_registry) -> None:
    StageRegistry.register("stub_silent_row_drop", mode="exceptional")(StubSilentRowDropStage)
    context = InMemoryStageContext(
        manifest=_manifest([_base_row(), _base_row("s2", "b.bin")]),
    )
    stage = StubSilentRowDropStage("stub_silent_row_drop", {})

    with pytest.raises(ValueError, match="without allow_partial_success=true"):
        ExceptionalStageExecutor().run(stage, context)


def test_filter_stage_may_reduce_rows_without_partial_flag() -> None:
    from plinth.base_stage import BaseStage
    from plinth.results import StageOutcome
    from plinth.runtime.executor import TypicalStageExecutor

    class FilterHalfStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(filters_rows=True, reads_files=False, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            if metadata["entity_id"] == "s1":
                return StageOutcome.filter()
            return StageOutcome.update(entity_id=metadata["entity_id"])

    context = InMemoryStageContext(
        manifest=_manifest([_base_row(), _base_row("s2", "b.bin")]),
    )
    stage = FilterHalfStage("filter_half", {})
    TypicalStageExecutor().run(stage, context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 1
