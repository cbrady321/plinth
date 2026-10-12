"""Config end_at_paths JSONPath cut semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.config import PipelineConfig
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import (
    experiment_dir,
    prepare_work_dir,
    register_golden_stages,
    run_pipeline,
    tier_config_path,
)


def test_end_at_paths_matches_end_at_stage_cut(tmp_path: Path) -> None:
    work_api = prepare_work_dir(tmp_path / "api", "gt2")
    run_pipeline("gt2", work_api, end_at_stage="allowlist_filter")
    exp_api = experiment_dir(work_api, "gt2")
    api_dirs = sorted(p.name for p in exp_api.iterdir() if p.is_dir())

    work_cfg = prepare_work_dir(tmp_path / "cfg", "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config.end_at_paths = ["$.gt2_root.children[0]"]
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work_cfg)
    pipeline.run(input_source=str(work_cfg / "data" / "dataset"))
    exp_cfg = experiment_dir(work_cfg, "gt2")
    cfg_dirs = sorted(p.name for p in exp_cfg.iterdir() if p.is_dir())

    assert api_dirs == cfg_dirs
    assert not any("golden_filter_b" in name for name in cfg_dirs)


def test_invalid_end_at_jsonpath_index_fails_loudly(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config.end_at_paths = ["$.gt2_root.children[99]"]
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(ValueError, match="out of range"):
        pipeline.run(input_source=str(work / "data" / "dataset"))


def test_invalid_end_at_paths_fail_loudly(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config.end_at_paths = ["nonexistent_stage_name"]
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(ValueError, match="not found in DAG"):
        pipeline.run(input_source=str(work / "data" / "dataset"))
