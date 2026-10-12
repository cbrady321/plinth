"""Stages that return plain dicts instead of StageOutcome are rejected."""

from __future__ import annotations

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.runtime.executor import TypicalStageExecutor


def test_plain_dict_return_rejected() -> None:
    class PlainDictStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            return {"category": "b"}

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
    stage = PlainDictStage("plain_dict", {})

    with pytest.raises(TypeError, match="expected StageOutcome"):
        TypicalStageExecutor().run(stage, context)
