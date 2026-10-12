"""Live manifest replace/merge and propagation proofs through TypicalStageExecutor."""

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


def _base_manifest() -> DatasetManifest:
    return DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1", "s2"],
                "batch": [1, 1],
                "slot": [None, None],
                "filename": ["a.bin", "b.bin"],
                "file_path": ["files/a.bin", "files/b.bin"],
            }
        )
    )


def test_column_update_merges_in_place_row_count_stable() -> None:
    manifest = _base_manifest()
    context = InMemoryStageContext(manifest=manifest)

    class TagStage(BaseStage):
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
            metadata: dict[str, Any],
        ) -> StageOutcome:
            return StageOutcome.update(tag="merged")

    TypicalStageExecutor().run(TagStage("tag", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 2
    assert all(result.df["tag"] == "merged")


def test_filter_stage_replaces_manifest_shape() -> None:
    manifest = _base_manifest()
    context = InMemoryStageContext(manifest=manifest)

    class DropBStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                required_input_columns={"filename"},
                filters_rows=True,
                reads_files=False,
                modifies_files=False,
            )

        def process_file(
            self,
            input_path: Path,
            output_path: Path,
            metadata: dict[str, Any],
        ) -> StageOutcome:
            if metadata.get("filename") == "b.bin":
                return StageOutcome.filter()
            return StageOutcome.update()

    TypicalStageExecutor().run(DropBStage("drop_b", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 1
    assert result.df.iloc[0]["filename"] == "a.bin"


def test_expand_stage_replaces_manifest_with_more_rows() -> None:
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

    class ExpandStage(BaseStage):
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

    TypicalStageExecutor().run(ExpandStage("expand", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 2


def test_modifies_files_false_keeps_file_reference() -> None:
    manifest = _base_manifest()
    context = InMemoryStageContext(manifest=manifest)

    class RefOnlyStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(
            self,
            input_path: Path,
            output_path: Path,
            metadata: dict[str, Any],
        ) -> StageOutcome:
            return StageOutcome.update(marker="ref")

    TypicalStageExecutor().run(RefOnlyStage("ref_only", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert result.df.iloc[0]["file_path"] == "files/a.bin"


def test_modifies_files_true_writes_output_file() -> None:
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
    file_path = Path(manifest.df.iloc[0]["file_path"])
    input_file = context.get_input_dir() / file_path
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"source-bytes")

    class CopyStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=True, modifies_files=True)

        def process_file(
            self,
            input_path: Path,
            output_path: Path,
            metadata: dict[str, Any],
        ) -> StageOutcome:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"copied")
            return StageOutcome.update(file_path=str(Path("files") / output_path.name))

    TypicalStageExecutor().run(CopyStage("copy", {}), context)
    out_dir = context.get_output_dir()
    copied = list(out_dir.rglob("*.bin"))
    assert copied
    assert copied[0].read_bytes() == b"copied"


def test_always_propagate_flag_available_on_stage_config() -> None:
    manifest = _base_manifest()
    context = InMemoryStageContext(manifest=manifest)

    class PropStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(
            self,
            input_path: Path,
            output_path: Path,
            metadata: dict[str, Any],
        ) -> StageOutcome:
            return StageOutcome.update(propagated=True)

    stage = PropStage("prop", {"_always_propagate": True})
    assert stage.config.get("_always_propagate") is True
    TypicalStageExecutor().run(stage, context)
    assert context.get_manifest() is not None
