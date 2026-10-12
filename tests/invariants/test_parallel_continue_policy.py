"""Parallel continue policy must not silently succeed with broken lineage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plinth.base_stage import BaseStage
from plinth.blocks import ParallelBlock, StageNode
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome


class _OkBranchStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(branch_marker="ok")


class _FailingBranchStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        raise RuntimeError("parallel branch failed")


def test_parallel_continue_policy_does_not_raise_but_produces_incomplete_outputs(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    StageRegistry.register("continue_ok_branch")(_OkBranchStage)
    StageRegistry.register("continue_fail_branch")(_FailingBranchStage)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    manifest = input_dir / "manifest.csv"
    manifest.write_text(
        "entity_id,batch,slot,filename,file_path\n"
        "s1,1,,a.bin,files/a.bin\n"
    )
    (input_dir / "files").mkdir()
    (input_dir / "files" / "a.bin").write_bytes(b"RIFF")

    output_dir = tmp_path / "output"
    config = {
        "params": {"continue_ok_branch": {}, "continue_fail_branch": {}},
        "parallel_error_policy": "continue",
    }
    parallel = ParallelBlock(
        "split",
        config,
        [StageNode("continue_ok_branch", config), StageNode("continue_fail_branch", config)],
    )
    result = parallel.execute([input_dir], output_dir, "a", parent_location_code="")
    assert len(result.output_dirs) == 1


def test_parallel_fail_fast_rejects_branch_failure(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    StageRegistry.register("failfast_ok_branch")(_OkBranchStage)
    StageRegistry.register("failfast_fail_branch")(_FailingBranchStage)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    manifest = input_dir / "manifest.csv"
    manifest.write_text(
        "entity_id,batch,slot,filename,file_path\n"
        "s1,1,,a.bin,files/a.bin\n"
    )
    (input_dir / "files").mkdir()
    (input_dir / "files" / "a.bin").write_bytes(b"RIFF")

    output_dir = tmp_path / "output"
    config = {
        "params": {"failfast_ok_branch": {}, "failfast_fail_branch": {}},
        "parallel_error_policy": "fail_fast",
    }
    parallel = ParallelBlock(
        "split",
        config,
        [StageNode("failfast_ok_branch", config), StageNode("failfast_fail_branch", config)],
    )
    with pytest.raises(ValueError, match="parallel branch failed"):
        parallel.execute([input_dir], output_dir, "a", parent_location_code="")
