"""Each typical stage shape (expand, aggregate, group_by, file-writing) run through the in-memory harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.runtime.executor import TypicalStageExecutor


def test_expand_rows_in_memory() -> None:
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

    class ExpandOneToTwoStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(expands_rows=True, reads_files=False, modifies_files=False)

        def process_file(
            self,
            input_path: Path,
            output_path: Path,
            metadata: dict[str, Any],
        ) -> StageOutcome:
            base = dict(metadata)
            return StageOutcome.expand(
                [
                    {**base, "slot": 1, "filename": "a_1.bin"},
                    {**base, "slot": 2, "filename": "a_2.bin"},
                ]
            )

    TypicalStageExecutor().run(ExpandOneToTwoStage("expand_demo", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 2


def test_group_by_process_group_in_memory() -> None:
    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["album_x", "album_x", "album_y"],
                "track": [1, 2, 7],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)

    class GroupCountStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                group_by=["entity_id"],
                reads_files=False,
                modifies_files=False,
            )

        def process_file(
            self,
            input_path: Path,
            output_path: Path,
            metadata: dict[str, Any],
        ) -> StageOutcome:
            return StageOutcome.update()

        def process_group(
            self,
            group_keys: dict[str, Any],
            rows: list[dict[str, Any]],
            input_dir: Path,
            output_dir: Path,
        ) -> StageOutcome:
            return StageOutcome.aggregate(
                entity_id=group_keys["entity_id"],
                child_count=len(rows),
            )

    TypicalStageExecutor().run(GroupCountStage("group_demo", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 2
    counts = sorted(result.df["child_count"].tolist())
    assert counts == [1, 2]


def test_modifies_files_in_memory() -> None:
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
    files_dir = manifest.df.iloc[0]["file_path"]
    context = InMemoryStageContext(manifest=manifest)
    input_file = context.get_input_dir() / files_dir
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"input")

    class TouchFileStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=True, modifies_files=True)

        def process_file(
            self,
            input_path: Path,
            output_path: Path,
            metadata: dict[str, Any],
        ) -> StageOutcome:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"processed")
            return StageOutcome.update(file_path=str(output_path.relative_to(context.get_output_dir())))

    TypicalStageExecutor().run(TouchFileStage("touch_file", {}), context)
    result = context.get_manifest()
    assert result is not None
    out_path = context.get_output_dir() / result.df.iloc[0]["file_path"]
    assert out_path.exists()
    assert out_path.read_bytes() == b"processed"
