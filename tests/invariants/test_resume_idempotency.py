"""Resume idempotency integration gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.config import PipelineConfig
from plinth.dataset.manifest_rows import normalize_manifest_rows
from plinth.runtime.pipeline import Pipeline
from plinth.runtime.resume_policy import (
    assert_upstream_manifests_unchanged,
    collect_manifest_snapshots,
    upstream_stage_names,
)
from tests.golden.run_harness import (
    experiment_dir,
    find_final_stage_dir,
    prepare_work_dir,
    register_golden_stages,
    run_pipeline,
    tier_config_path,
)


def _full_run_manifest(work: Path, tier: str) -> tuple[dict, ...]:
    run_pipeline(tier, work)
    exp = experiment_dir(work, tier)
    final_dir = find_final_stage_dir(exp)
    return normalize_manifest_rows(final_dir / "manifest.csv")


RESUME_MIDDLE_STAGES = {
    "gt2": "tag_category",
    "gt3": "allowlist_filter",
    "gt5": "golden_join_filter",
}


@pytest.mark.parametrize("tier", ["gt2", "gt3", "gt5"])
def test_resume_from_middle_matches_full_run(tmp_path: Path, tier: str) -> None:
    work = prepare_work_dir(tmp_path, tier)
    full_manifest = _full_run_manifest(work, tier)

    config = PipelineConfig.from_yaml(tier_config_path(tier))
    dag_root = config.build_dag()
    resume_stage = RESUME_MIDDLE_STAGES[tier]

    exp = experiment_dir(work, tier)
    before = collect_manifest_snapshots(exp)
    upstream = [
        name
        for name in upstream_stage_names(dag_root, resume_stage)
        if name in before
    ]

    register_golden_stages()
    pipeline = Pipeline(config, f"golden_{tier}", work)
    pipeline.run(
        input_source=str(work / "data" / "dataset"),
        start_from_stage=resume_stage,
    )

    after = collect_manifest_snapshots(exp)
    if upstream:
        assert_upstream_manifests_unchanged(before, after, upstream)

    final_dir = find_final_stage_dir(exp)
    resume_manifest = normalize_manifest_rows(final_dir / "manifest.csv")
    assert resume_manifest == full_manifest


def test_resume_from_first_stage_matches_full_run(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    full_manifest = _full_run_manifest(work, "gt2")

    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    dag_root = config.build_dag()
    first_stage = dag_root.get_all_stage_names()[0]

    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)
    pipeline.run(
        input_source=str(work / "data" / "dataset"),
        start_from_stage=first_stage,
    )

    exp = experiment_dir(work, "gt2")
    final_dir = find_final_stage_dir(exp)
    assert normalize_manifest_rows(final_dir / "manifest.csv") == full_manifest


def test_resume_with_missing_upstream_fails_clearly(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    register_golden_stages()
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises((ValueError, FileNotFoundError, RuntimeError)):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="golden_filter_b",
        )


def test_resume_preserves_parallel_branch_upstream(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt3")
    full_manifest = _full_run_manifest(work, "gt3")

    config = PipelineConfig.from_yaml(tier_config_path("gt3"))
    dag_root = config.build_dag()
    resume_stage = "allowlist_filter"

    exp = experiment_dir(work, "gt3")
    before = collect_manifest_snapshots(exp)
    upstream = upstream_stage_names(dag_root, resume_stage)

    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt3", work)
    pipeline.run(
        input_source=str(work / "data" / "dataset"),
        start_from_stage=resume_stage,
    )

    after = collect_manifest_snapshots(exp)
    assert_upstream_manifests_unchanged(before, after, upstream)
    assert "golden_branch_a" in before
    assert "golden_branch_b" in before

    final_dir = find_final_stage_dir(exp)
    assert normalize_manifest_rows(final_dir / "manifest.csv") == full_manifest


def test_jsonpath_start_matches_named_start_from_stage(tmp_path: Path) -> None:
    work_a = prepare_work_dir(tmp_path / "a", "gt2")
    work_b = prepare_work_dir(tmp_path / "b", "gt2")

    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    resume_stage = "tag_category"
    jsonpath = "$.gt2_root.children[1]"

    run_pipeline("gt2", work_a)
    register_golden_stages()
    pipeline_a = Pipeline(config, "golden_gt2", work_a)
    pipeline_a.run(
        input_source=str(work_a / "data" / "dataset"),
        start_from_stage=resume_stage,
    )

    run_pipeline("gt2", work_b)
    config_b = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config_b.start_from_paths = [jsonpath]
    register_golden_stages()
    pipeline_b = Pipeline(config_b, "golden_gt2", work_b)
    pipeline_b.run(input_source=str(work_b / "data" / "dataset"))

    exp_a = experiment_dir(work_a, "gt2")
    exp_b = experiment_dir(work_b, "gt2")
    manifest_a = normalize_manifest_rows(find_final_stage_dir(exp_a) / "manifest.csv")
    manifest_b = normalize_manifest_rows(find_final_stage_dir(exp_b) / "manifest.csv")
    assert manifest_a == manifest_b
