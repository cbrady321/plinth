"""InMemoryStageContext harness tests."""

from __future__ import annotations

import pandas as pd

from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.results import StageOutcome
from tests.hermetic_stages import HermeticAllowlistFilterStage


def test_allowlist_filter_in_memory_harness() -> None:
    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1", "s2"],
                "batch": [1, 1],
                "slot": [None, None],
                "filename": ["keep.bin", "drop.bin"],
                "file_path": ["files/keep.bin", "files/drop.bin"],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)
    stage = HermeticAllowlistFilterStage(
        "allowlist_filter",
        {"allow": ["keep.bin"]},
    )
    stage.execute(context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 1
    assert result.df.iloc[0]["filename"] == "keep.bin"


def test_stage_outcome_filter_in_memory() -> None:
    from plinth.base_stage import BaseStage
    from plinth.intent import StageIntent

    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1"],
                "batch": [1],
                "slot": [None],
                "filename": ["x.bin"],
                "file_path": ["files/x.bin"],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)

    class FilterAllStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(filters_rows=True, reads_files=False, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            return StageOutcome.filter()

    stage = FilterAllStage("filter_all", {})
    stage.execute(context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 0


def test_allowlist_filter_case_insensitive_in_memory() -> None:
    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1", "s2"],
                "batch": [1, 1],
                "slot": [None, None],
                "filename": ["KEEP.bin", "drop.bin"],
                "file_path": ["files/KEEP.bin", "files/drop.bin"],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)
    stage = HermeticAllowlistFilterStage(
        "allowlist_filter",
        {"allow": ["keep.bin"], "case_insensitive": True},
    )
    stage.execute(context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 1
    assert result.df.iloc[0]["filename"] == "KEEP.bin"
