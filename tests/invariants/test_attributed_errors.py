"""Attributed error message tests."""

from __future__ import annotations

import re

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.runtime.executor import TypicalStageExecutor

STAGE_FIELD_SECTION = re.compile(
    r"Stage \w+|StageIntent\.|author contract §"
)


def test_row_failure_message_cites_contract() -> None:
    class FailingStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            raise RuntimeError("boom")

    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1"],
                "batch": [1],
                "slot": [None],
                "filename": ["a.bin"],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)
    stage = FailingStage("fail_stage", {})

    with pytest.raises(ValueError, match="author contract §Row failure policy") as exc:
        TypicalStageExecutor().run(stage, context)
    assert STAGE_FIELD_SECTION.search(str(exc.value))


def test_missing_input_columns_message_cites_intent() -> None:
    class NeedsColumnStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                required_input_columns={"missing_col"},
                reads_files=False,
                modifies_files=False,
            )

        def process_file(self, input_path, output_path, metadata):
            return StageOutcome.update()

    manifest = DatasetManifest(pd.DataFrame({"entity_id": ["s1"]}))
    context = InMemoryStageContext(manifest=manifest)
    stage = NeedsColumnStage("needs_col", {})

    with pytest.raises(ValueError, match="StageIntent.required_input_columns") as exc:
        TypicalStageExecutor().run(stage, context)
    assert "needs_col" in str(exc.value)
