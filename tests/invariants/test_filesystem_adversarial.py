"""On-disk adversarial failure modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.context import FileSystemStageContext, MultiInputStageContext
from plinth.dataset.structures import DatasetManifest, MetadataLedger
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.runtime.executor import TypicalStageExecutor
from plinth.runtime.hash_chain_validator import validate_hash_chain
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import (
    experiment_dir,
    prepare_work_dir,
    register_golden_stages,
    run_pipeline,
    tier_config_path,
)


def test_truncated_ledger_yaml_on_disk_fails_validation(tmp_path: Path) -> None:
    ledger_path = tmp_path / "metadata_ledger.yaml"
    ledger_path.write_text("# truncated\nentries:\n  - stage_name: s1\n    input_hash: ")
    with pytest.raises((ValueError, KeyError, TypeError)):
        MetadataLedger.from_yaml(ledger_path)


def test_corrupt_ledger_chain_on_disk_fails_validation(tmp_path: Path) -> None:
    from plinth.dataset.structures import MetadataLedgerEntry

    ledger = MetadataLedger(
        entries=[
            MetadataLedgerEntry(
                stage_name="s1",
                timestamp="2026-01-01T00:00:00",
                function_name="T",
                input_directory="/in",
                output_directory="/out",
                input_hash="0" * 64,
                output_hash="aaa",
                params_hash="p",
                params={},
                files_processed=1,
                duration_seconds=1.0,
            ),
            MetadataLedgerEntry(
                stage_name="s2",
                timestamp="2026-01-01T00:00:01",
                function_name="T",
                input_directory="/in",
                output_directory="/out",
                input_hash="broken",
                output_hash="bbb",
                params_hash="p",
                params={},
                files_processed=1,
                duration_seconds=1.0,
            ),
        ]
    )
    ledger_path = tmp_path / "metadata_ledger.yaml"
    ledger.to_yaml(ledger_path)
    loaded = MetadataLedger.from_yaml(ledger_path)
    with pytest.raises(ValueError, match="hash-chain break"):
        validate_hash_chain(loaded)


def test_empty_manifest_csv_fails_required_columns(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    pd.DataFrame(
        {
            "entity_id": ["s1"],
            "batch": [1],
            "slot": [None],
        }
    ).to_csv(input_dir / "manifest.csv", index=False)

    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1"],
                "batch": [1],
                "slot": [None],
            }
        )
    )
    context = FileSystemStageContext(input_dir, output_dir, manifest)

    class NeedsFilenameStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(required_input_columns={"filename"}, reads_files=False, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
            return StageOutcome.update()

    with pytest.raises(ValueError, match="requires input columns"):
        TypicalStageExecutor().run(NeedsFilenameStage("needs_file", {}), context)


def test_empty_input_file_fails_fail_fast(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    files_dir = input_dir / "files"
    files_dir.mkdir(parents=True)
    (files_dir / "a.bin").write_bytes(b"")
    pd.DataFrame(
        {
            "entity_id": ["s1"],
            "batch": [1],
            "slot": [None],
            "filename": ["a.bin"],
            "file_path": ["files/a.bin"],
        }
    ).to_csv(input_dir / "manifest.csv", index=False)

    manifest = DatasetManifest(pd.read_csv(input_dir / "manifest.csv"))
    context = FileSystemStageContext(input_dir, tmp_path / "out", manifest)

    class ReadFileStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=True, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
            if input_path.stat().st_size == 0:
                raise ValueError("empty file")
            return StageOutcome.update()

    with pytest.raises(ValueError, match="empty file|Row failure"):
        TypicalStageExecutor().run(ReadFileStage("read_file", {}), context)


def test_missing_input_file_fails_fail_fast(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    files_dir = input_dir / "files"
    files_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "entity_id": ["s1"],
            "batch": [1],
            "slot": [None],
            "filename": ["a.bin"],
            "file_path": ["files/missing.bin"],
        }
    ).to_csv(input_dir / "manifest.csv", index=False)

    manifest = DatasetManifest(pd.read_csv(input_dir / "manifest.csv"))
    context = FileSystemStageContext(input_dir, tmp_path / "out", manifest)

    class ReadFileStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=True, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
            if not input_path.exists():
                raise ValueError("missing file")
            return StageOutcome.update()

    with pytest.raises(ValueError, match="missing file|Row failure"):
        TypicalStageExecutor().run(ReadFileStage("read_file", {}), context)


def test_file_path_traversal_rejected(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"RIFF")
    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1"],
                "batch": [1],
                "slot": [None],
                "filename": ["a.bin"],
                "file_path": ["../outside.bin"],
            }
        )
    )
    context = FileSystemStageContext(input_dir, tmp_path / "out", manifest)

    with pytest.raises(ValueError, match="outside input directory"):
        context.get_input_path(entity_id="s1", batch=1)


def test_schema_mismatch_on_disk_merge_fails(tmp_path: Path) -> None:
    def _write_input(root: Path, extra_col: str) -> Path:
        d = root / "input"
        d.mkdir(parents=True)
        (d / "manifest.csv").write_text(
            "entity_id,batch,slot,filename,file_path\n"
            "s1,1,,a.bin,files/a.bin\n"
        )
        (d / "dataset_schema.yaml").write_text(
            "schema_format: 1\n"
            f"unique_key: [entity_id, batch, slot, {extra_col}]\n"
            "columns:\n  entity_id: str\n  batch: int\n  slot: int\n"
            f"  filename: str\n  file_path: str\n  {extra_col}: str\n"
        )
        return d

    input_a = _write_input(tmp_path / "a", "tag_a")
    input_b = _write_input(tmp_path / "b", "tag_b")

    ctx = MultiInputStageContext(
        input_dirs=[input_a, input_b],
        output_dir=tmp_path / "merged",
        manifest=None,
    )
    with pytest.raises(ValueError, match="Schema mismatch"):
        ctx.get_schema()


def test_missing_manifest_at_resume_input_fails_loudly(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    run_pipeline("gt2", work, end_at_stage="allowlist_filter")
    exp = experiment_dir(work, "gt2")
    filter_dirs = [p for p in exp.iterdir() if p.is_dir() and "allowlist_filter" in p.name]
    (filter_dirs[0] / "manifest.csv").unlink()

    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(ValueError, match="no manifest available"):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="tag_category",
        )


def test_unparseable_manifest_csv_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    path.write_text('entity_id,file_path\n"s1,files/a.bin\n')
    with pytest.raises(ValueError, match="Failed to load manifest"):
        DatasetManifest.from_csv(path)


def test_zero_byte_manifest_csv_is_an_empty_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    path.write_text("")
    assert len(DatasetManifest.from_csv(path)) == 0
