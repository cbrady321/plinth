"""Typing tests for CoreManifestRow (E50).

This module is type-checked by mypy in CI (``mypy src/plinth tests/typing``).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.media import NO_SOURCE_FILE
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.rows import CoreManifestRow


class DocumentRow(CoreManifestRow, total=False):
    """A consumer-side extension: the documented way to type dataset-specific columns."""

    page: int
    text_path: str


class _TypedRowStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            write_columns={"tag": "str"},
            reads_files=False,
            modifies_files=False,
        )

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        metadata: CoreManifestRow,
    ) -> StageOutcome:
        entity: str | None = metadata.get("entity_id")
        source: str | None = metadata.get("source_path")
        return StageOutcome.update(tag=f"{entity}:{source}")


class _ExtendedRowStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(write_columns={"next_page": "int"}, reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: CoreManifestRow) -> StageOutcome:
        row = cast(DocumentRow, metadata)
        page: int = row.get("page", 0)
        return StageOutcome.update(next_page=page + 1)


def test_core_manifest_row_stage_runs_with_typed_signature() -> None:
    manifest = DatasetManifest(pd.DataFrame({"entity_id": ["s1"], "value": [1]}))
    context = InMemoryStageContext(manifest=manifest)
    from plinth.runtime.executor import TypicalStageExecutor

    TypicalStageExecutor().run(_TypedRowStage("typed_row", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert result.df.loc[0, "tag"] == f"s1:{NO_SOURCE_FILE}"


def test_extended_row_type_runs() -> None:
    from plinth.runtime.executor import TypicalStageExecutor

    manifest = DatasetManifest(pd.DataFrame({"entity_id": ["d1"], "page": [3]}))
    context = InMemoryStageContext(manifest=manifest)
    TypicalStageExecutor().run(_ExtendedRowStage("extended_row", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert result.df.loc[0, "next_page"] == 4


def test_core_manifest_row_not_runtime_validated() -> None:
    """Missing core keys and extra domain keys must not fail."""
    from plinth.runtime.executor import TypicalStageExecutor

    class _LooseRowStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: CoreManifestRow) -> StageOutcome:
            assert dict(metadata)["custom_domain_col"] == "present"
            return StageOutcome.update()

    manifest = DatasetManifest(pd.DataFrame({"custom_domain_col": ["present"]}))
    context = InMemoryStageContext(manifest=manifest)
    TypicalStageExecutor().run(_LooseRowStage("loose_row", {}), context)
