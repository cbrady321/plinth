"""Row failure policy tests."""

from __future__ import annotations

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.results import StageOutcome


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


def test_fail_fast_on_domain_exception() -> None:
    class ExplodingStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            raise RuntimeError("boom")

    context = InMemoryStageContext(manifest=_manifest([_base_row(), _base_row("s2", "b.bin")]))
    stage = ExplodingStage("explode", {})

    with pytest.raises(ValueError, match="failed at row 0"):
        stage.execute(context)


def test_partial_success_records_dropped_rows() -> None:
    class ExplodingStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                reads_files=False,
                modifies_files=False,
                allow_partial_success=True,
                max_dropped_rows=1,
            )

        def process_file(self, input_path, output_path, metadata):
            if metadata["entity_id"] == "s1":
                raise RuntimeError("boom")
            return StageOutcome.update(entity_id=metadata["entity_id"])

    context = InMemoryStageContext(manifest=_manifest([_base_row(), _base_row("s2", "b.bin")]))
    stage = ExplodingStage("explode", {})
    stage.execute(context)

    assert stage._dropped_rows == 1
    assert stage._files_processed == 1


def test_partial_success_exceeding_max_dropped_rows_fails() -> None:
    class ExplodingStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                reads_files=False,
                modifies_files=False,
                allow_partial_success=True,
                max_dropped_rows=0,
            )

        def process_file(self, input_path, output_path, metadata):
            raise RuntimeError("boom")

    context = InMemoryStageContext(manifest=_manifest([_base_row()]))
    stage = ExplodingStage("explode", {})

    with pytest.raises(ValueError, match="StageIntent.max_dropped_rows"):
        stage.execute(context)


def test_fail_fast_on_missing_input_file() -> None:
    class PassthroughStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=True, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            return StageOutcome.update(metadata)

    context = InMemoryStageContext(manifest=_manifest([_base_row()]))
    stage = PassthroughStage("passthrough", {})

    with pytest.raises(ValueError, match="failed at row 0"):
        stage.execute(context)
