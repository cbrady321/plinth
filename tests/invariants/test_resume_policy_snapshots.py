"""collect_manifest_snapshots finds nested parallel branch manifests."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.runtime.resume_policy import collect_manifest_snapshots
from tests.golden.run_harness import experiment_dir, prepare_work_dir, run_pipeline


@pytest.mark.parametrize("tier", ["gt3", "gt6"])
def test_nested_parallel_branch_snapshots_indexed_by_stage_name(tmp_path: Path, tier: str) -> None:
    work = prepare_work_dir(tmp_path, tier)
    run_pipeline(tier, work)
    exp = experiment_dir(work, tier)
    snapshots = collect_manifest_snapshots(exp)
    assert "golden_branch_a" in snapshots
    assert "golden_branch_b" in snapshots
    assert len(snapshots["golden_branch_a"].rows) >= 1
