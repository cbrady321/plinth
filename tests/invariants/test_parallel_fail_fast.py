"""Parallel branch fail-fast integration gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from plinth.base_stage import BaseStage
from plinth.blocks import ParallelBlock, StageNode
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome


class _OkBranchStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(branch_marker="ok")


class _FailingBranchStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        raise RuntimeError("parallel branch failed")


def test_parallel_block_fail_fast_aborts_on_first_branch_failure(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    StageRegistry.register("healthy_branch")(_OkBranchStage)
    StageRegistry.register("broken_branch")(_FailingBranchStage)

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
        "params": {"healthy_branch": {}, "broken_branch": {}},
        "parallel_error_policy": "fail_fast",
    }
    parallel = ParallelBlock(
        "split",
        config,
        [StageNode("healthy_branch", config), StageNode("broken_branch", config)],
    )
    with pytest.raises(ValueError, match="parallel branch failed"):
        parallel.execute([input_dir], output_dir, "a", parent_location_code="")
