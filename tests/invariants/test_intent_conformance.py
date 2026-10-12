"""Output/intent conformance tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.runtime.intent_conformance import verify_output_intent_conformance


def test_filters_rows_cannot_increase_row_count_direct() -> None:
    intent = StageIntent(filters_rows=True)
    input_manifest = DatasetManifest(pd.DataFrame({"entity_id": ["s1"]}))
    output_manifest = DatasetManifest(pd.DataFrame({"entity_id": ["s1", "s2"]}))
    stage = Mock(stage_name="bad_filter")

    with pytest.raises(ValueError, match="filters_rows=True but output row count"):
        verify_output_intent_conformance(
            stage,
            intent,
            input_manifest,
            output_manifest,
            Path("."),
        )


def test_missing_declared_output_columns_fail() -> None:
    class MissingColumnStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                write_columns={"expected_col": "str"},
                reads_files=False,
                modifies_files=False,
            )

        def process_file(self, input_path, output_path, metadata):
            return StageOutcome.update()

    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1"],
                "batch": [1],
                "slot": [None],
                "filename": ["a.bin"],
                "file_path": ["files/a.bin"],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)
    stage = MissingColumnStage("missing_col", {})

    with pytest.raises(ValueError, match="declared output columns"):
        stage.execute(context)
