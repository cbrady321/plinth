"""Adversarial negative corpus for silent-failure classes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.blocks import ParallelBlock, StageNode
from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest, MetadataLedger, MetadataLedgerEntry
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome
from plinth.runtime.executor import TypicalStageExecutor
from plinth.runtime.hash_chain_validator import validate_hash_chain


def test_empty_manifest_handoff_fails_on_required_columns() -> None:
    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1"],
                "batch": [1],
                "slot": [None],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)

    class NeedsFilenameStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                required_input_columns={"filename"},
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

    with pytest.raises(ValueError, match="requires input columns"):
        TypicalStageExecutor().run(NeedsFilenameStage("needs_file", {}), context)


def test_duplicate_unique_keys_after_expand_rejected() -> None:
    from plinth.dataset.structures import DatasetSchema

    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1", "s1"],
                "batch": [1, 1],
                "slot": [None, None],
                "filename": ["a.bin", "a.bin"],
            }
        )
    )
    schema = DatasetSchema(
        unique_key=["entity_id", "batch", "slot", "filename"],
        columns={
            "entity_id": "str",
            "batch": "int",
            "slot": "int",
            "filename": "str",
        },
    )
    with pytest.raises(ValueError, match="Duplicate entries"):
        schema.validate_dataframe(manifest.df)


def test_parallel_unique_key_mutation_rejected_at_runtime(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    class AppendKeyStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(
                append_to_unique_key={"copy_index"},
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

    StageRegistry.register("append_key_branch")(AppendKeyStage)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "manifest.csv").write_text(
        "entity_id,batch,slot,filename,file_path\n"
        "s1,1,,a.bin,files/a.bin\n"
    )
    (input_dir / "files").mkdir()
    (input_dir / "files" / "a.bin").write_bytes(b"RIFF")

    config = {"params": {"append_key_branch": {}}}
    parallel = ParallelBlock(
        "par",
        config,
        [StageNode("append_key_branch", config)],
    )
    with pytest.raises(ValueError, match="append to unique key"):
        parallel.execute([input_dir], tmp_path / "out", "a", parent_location_code="")


def test_corrupt_ledger_fails_hash_chain_validation() -> None:
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
    with pytest.raises(ValueError, match="hash-chain break"):
        validate_hash_chain(ledger)


def test_parallel_join_schema_mismatch_fails_merge(tmp_path: Path) -> None:
    def _write_input(name: str, extra_col: str) -> Path:
        d = tmp_path / name
        d.mkdir()
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
        (d / "files").mkdir()
        (d / "files" / "a.bin").write_bytes(b"RIFF")
        return d

    from plinth.context import MultiInputStageContext

    input_a = _write_input("in_a", "tag_a")
    input_b = _write_input("in_b", "tag_b")

    ctx = MultiInputStageContext(
        input_dirs=[input_a, input_b],
        output_dir=tmp_path / "merged",
        manifest=None,
    )
    with pytest.raises(ValueError, match="Schema mismatch"):
        ctx.get_schema()
