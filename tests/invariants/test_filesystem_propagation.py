"""On-disk manifest propagation proofs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.context import FileSystemStageContext, MultiInputStageContext
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.runtime.executor import TypicalStageExecutor
from tests.golden.run_harness import experiment_dir, prepare_work_dir, run_pipeline
from tests.hermetic_stages import HermeticTagCategoryStage


def _write_input_tree(root: Path) -> Path:
    input_dir = root / "input"
    input_dir.mkdir(parents=True)
    files_dir = input_dir / "files"
    files_dir.mkdir()
    (files_dir / "a.bin").write_bytes(b"file-a-bytes")
    (files_dir / "b.bin").write_bytes(b"file-b-bytes")
    manifest = pd.DataFrame(
        {
            "entity_id": ["s1", "s2"],
            "batch": [1, 1],
            "slot": [None, None],
            "filename": ["a.bin", "b.bin"],
            "file_path": ["files/a.bin", "files/b.bin"],
        }
    )
    manifest.to_csv(input_dir / "manifest.csv", index=False)
    schema = DatasetSchema(
        unique_key=["entity_id", "batch", "slot", "filename"],
        columns={
            "entity_id": "str",
            "batch": "int",
            "slot": "int",
            "filename": "str",
            "file_path": "str",
        },
    )
    schema.to_yaml(input_dir / "dataset_schema.yaml")
    return input_dir


def test_modifies_files_true_copies_files_on_disk(tmp_path: Path) -> None:
    input_dir = _write_input_tree(tmp_path)
    output_dir = tmp_path / "stage_out"
    manifest = DatasetManifest(pd.read_csv(input_dir / "manifest.csv"))
    context = FileSystemStageContext(input_dir, output_dir, manifest)

    stage = HermeticTagCategoryStage(
        "tag_category",
        {"default_category": "fs_category"},
    )
    TypicalStageExecutor().run(stage, context)

    copied = list(output_dir.rglob("a.bin"))
    assert copied
    assert copied[0].read_bytes() == b"file-a-bytes"
    result = context.get_manifest()
    assert result is not None
    assert str(result.df.iloc[0]["file_path"]).startswith("files/")


def test_modifies_files_false_keeps_reference_paths(tmp_path: Path) -> None:
    input_dir = _write_input_tree(tmp_path)
    output_dir = tmp_path / "ref_out"
    manifest = DatasetManifest(pd.read_csv(input_dir / "manifest.csv"))
    context = FileSystemStageContext(input_dir, output_dir, manifest)

    class RefOnlyStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict) -> StageOutcome:
            return StageOutcome.update(marker="ref")

    TypicalStageExecutor().run(RefOnlyStage("ref_only", {}), context)
    result = context.get_manifest()
    assert result is not None
    assert result.df.iloc[0]["file_path"] == "files/a.bin"
    assert not list(output_dir.rglob("*.bin"))


def test_multi_input_merge_contains_parallel_branch_columns(tmp_path: Path) -> None:
    branch_a = tmp_path / "branch_a"
    branch_b = tmp_path / "branch_b"
    for root, col in ((branch_a, "branch_a"), (branch_b, "branch_b")):
        input_dir = _write_input_tree(root)
        manifest_path = input_dir / "manifest.csv"
        df = pd.read_csv(manifest_path)
        df[col] = "x"
        df.to_csv(manifest_path, index=False)
        schema_path = input_dir / "dataset_schema.yaml"
        schema = DatasetSchema.from_yaml(schema_path)
        schema.columns[col] = "str"
        schema.to_yaml(schema_path)

    merged_dir = tmp_path / "merged"
    ctx = MultiInputStageContext(
        input_dirs=[branch_a / "input", branch_b / "input"],
        output_dir=merged_dir,
        manifest=None,
    )
    merged = ctx.get_manifest()
    assert merged is not None
    assert "branch_a" in merged.df.columns
    assert "branch_b" in merged.df.columns


def test_gt2_pipeline_tag_category_manifest_on_disk(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    run_pipeline("gt2", work, end_at_stage="tag_category")
    exp = experiment_dir(work, "gt2")
    stage_dir = exp / "03_tag_category"
    manifest = pd.read_csv(stage_dir / "manifest.csv")
    assert "category" in manifest.columns
    assert str(manifest.iloc[0]["file_path"]).startswith("files/")
