"""aggregate_outputs block setting controls parallel merge behavior."""

from __future__ import annotations

from pathlib import Path

from tests.golden.run_harness import experiment_dir, prepare_work_dir, run_pipeline


def test_gt5_parallel_branches_remain_separate_without_merge(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt5")
    run_pipeline("gt5", work)
    exp = experiment_dir(work, "gt5")

    branch_a_dirs = [p for p in exp.rglob("*golden_branch_a*") if (p / "manifest.csv").exists()]
    branch_b_dirs = [p for p in exp.rglob("*golden_branch_b*") if (p / "manifest.csv").exists()]
    assert branch_a_dirs
    assert branch_b_dirs
    assert branch_a_dirs[0] != branch_b_dirs[0]


def test_gt10_parallel_branches_merge_before_join(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt10")
    run_pipeline("gt10", work)
    exp = experiment_dir(work, "gt10")

    join_dirs = [p for p in exp.rglob("*golden_join_filter*") if (p / "manifest.csv").exists()]
    assert join_dirs
    manifest_path = join_dirs[0] / "manifest.csv"
    text = manifest_path.read_text()
    assert "branch_a" in text or "branch_b" in text
