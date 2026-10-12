"""Hypothesis fuzz for TypicalStageExecutor intent/outcome invariants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.runtime.executor import TypicalStageExecutor


def _manifest(rows: int) -> DatasetManifest:
    return DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": [f"s{i}" for i in range(rows)],
                "batch": [1] * rows,
                "slot": [None] * rows,
                "filename": [f"f{i}.bin" for i in range(rows)],
            }
        )
    )


@pytest.mark.property
@given(rows=st.integers(min_value=1, max_value=5))
def test_update_never_drops_rows_without_structural_flags(rows: int) -> None:
    manifest = _manifest(rows)
    context = InMemoryStageContext(manifest=manifest)

    class TagStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(write_columns={"tag": "str"}, reads_files=False, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
            return StageOutcome.update(tag="ok")

    TypicalStageExecutor().run(TagStage("tag", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == rows
    assert "tag" in result.df.columns


@pytest.mark.property
@given(rows=st.integers(min_value=1, max_value=4))
def test_filter_reduces_or_preserves_row_count(rows: int) -> None:
    manifest = _manifest(rows)
    context = InMemoryStageContext(manifest=manifest)

    class DropFirstStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(filters_rows=True, reads_files=False, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
            if metadata.get("filename") == "f0.bin":
                return StageOutcome.filter()
            return StageOutcome.update()

    TypicalStageExecutor().run(DropFirstStage("drop", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) <= rows
