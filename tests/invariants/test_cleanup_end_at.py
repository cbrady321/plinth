"""Live end_at_stage and JSONPath cleanup behavioral tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.config import PipelineConfig
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import experiment_dir, prepare_work_dir, register_golden_stages, tier_config_path


def test_end_at_stage_stops_before_downstream_nodes(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)
    pipeline.run(
        input_source=str(work / "data" / "dataset"),
        end_at_stage="allowlist_filter",
    )

    exp = experiment_dir(work, "gt2")
    stage_dirs = [p.name for p in exp.iterdir() if p.is_dir()]
    assert any("allowlist_filter" in name for name in stage_dirs)
    assert not any("golden_filter_b" in name for name in stage_dirs)


def test_end_at_stage_leaves_no_partial_dirs_beyond_cut(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)
    pipeline.run(
        input_source=str(work / "data" / "dataset"),
        end_at_stage="tag_category",
    )

    exp = experiment_dir(work, "gt2")
    names = sorted(p.name for p in exp.iterdir() if p.is_dir())
    assert any("tag_category" in n for n in names)
    assert not any("golden_filter_b" in n for n in names)


def test_invalid_skip_stage_name_fails_loudly(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(ValueError, match="not found in DAG"):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="nonexistent_stage_xyz",
        )


def test_mismatched_jsonpath_start_fails_or_no_silent_empty_run(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config.start_from_paths = ["$.gt2_root.children[99]"]
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(ValueError, match="out of range"):
        pipeline.run(input_source=str(work / "data" / "dataset"))
