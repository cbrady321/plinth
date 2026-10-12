"""Wrong-stage negative corpus."""

from __future__ import annotations

import pytest

from plinth.intent import StageIntent


def test_strict_intent_rejects_redundant_replaces_manifest() -> None:
    intent = StageIntent(
        required_input_columns={"entity_id"},
        write_columns={"category": "str"},
        replaces_manifest=True,
        filters_rows=True,
    )
    with pytest.raises(ValueError, match="replaces_manifest=True is redundant"):
        intent.validate_strict()


def test_executor_rejects_missing_required_columns() -> None:
    import pandas as pd

    from plinth.base_stage import BaseStage
    from plinth.context import InMemoryStageContext
    from plinth.dataset.structures import DatasetManifest
    from plinth.intent import StageIntent
    from plinth.results import StageOutcome
    from plinth.runtime.executor import TypicalStageExecutor

    class NeedsCategoryStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(required_input_columns={"category"})

        def process_file(self, input_path, output_path, metadata):
            return StageOutcome.update()

    manifest = DatasetManifest(
        pd.DataFrame({"entity_id": ["s1"], "batch": [1], "slot": [None]})
    )
    context = InMemoryStageContext(manifest=manifest)
    stage = NeedsCategoryStage("needs_category", {})

    with pytest.raises(ValueError, match="requires input columns"):
        TypicalStageExecutor().run(stage, context)
