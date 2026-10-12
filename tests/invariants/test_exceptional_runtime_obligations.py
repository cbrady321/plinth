"""Runtime exceptional obligation verification tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.context import FileSystemStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.registry import ExceptionalObligations, StageRegistry
from plinth.runtime.exceptional_executor import ExceptionalStageExecutor
from plinth.runtime.exceptional_obligation_verifier import ExceptionalObligationError


def _seed_input(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "02_good_exceptional"
    input_dir.mkdir()
    output_dir.mkdir()
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
    manifest.to_csv(input_dir / "manifest.csv")
    return input_dir, output_dir


def test_compliant_exceptional_stage_passes(isolated_registry: None, tmp_path: Path) -> None:
    from plinth.runtime.hashing import compute_directory_hash, compute_params_hash
    from plinth.runtime.ledger_writer import LedgerWriter

    @StageRegistry.register("good_exceptional", mode="exceptional")
    class GoodExceptionalStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            raise NotImplementedError

        def execute(self, context):
            output_dir = context.get_output_dir()
            manifest = context.get_manifest()
            if manifest is not None:
                context.update_manifest(manifest, replace=True)
            ledger = context.get_ledger()
            input_dir = context.get_input_dir()
            LedgerWriter().append_entry(
                ledger,
                stage_name=self.stage_name,
                function_name=self.__class__.__name__,
                input_directory=str(input_dir),
                output_directory=str(output_dir),
                input_hash=compute_directory_hash(input_dir),
                output_hash=compute_directory_hash(output_dir),
                params_hash=compute_params_hash(self.config),
                params=dict(self.config),
                files_processed=1,
                duration_seconds=0.01,
            )
            LedgerWriter().write(ledger, output_dir)
            return output_dir

    input_dir, output_dir = _seed_input(tmp_path)
    context = FileSystemStageContext(input_dir, output_dir)
    stage = GoodExceptionalStage("good_exceptional", {})
    ExceptionalStageExecutor().run(stage, context)
    assert (output_dir / "metadata_ledger.yaml").exists()


def test_missing_ledger_raises_obligation_error(isolated_registry: None, tmp_path: Path) -> None:
    @StageRegistry.register("bad_exceptional", mode="exceptional", obligations=ExceptionalObligations())
    class BadExceptionalStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path, output_path, metadata):
            raise NotImplementedError

        def execute(self, context):
            manifest = context.get_manifest()
            if manifest is not None:
                context.update_manifest(manifest, replace=True)
            return context.get_output_dir()

    input_dir, output_dir = _seed_input(tmp_path)
    context = FileSystemStageContext(input_dir, output_dir)
    stage = BadExceptionalStage("bad_exceptional", {})

    with pytest.raises(ExceptionalObligationError, match="records_ledger"):
        ExceptionalStageExecutor().run(stage, context)


def test_obligation_error_attributes(isolated_registry: None, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "02_stage"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "manifest.csv").write_text("entity_id,batch,slot,filename,file_path\n")

    from plinth.runtime.exceptional_obligation_verifier import verify_exceptional_obligations

    context = FileSystemStageContext(input_dir, output_dir)
    with pytest.raises(ExceptionalObligationError) as exc:
        verify_exceptional_obligations("x", context, input_ledger_entries=0)

    assert exc.value.obligation == "records_ledger"
