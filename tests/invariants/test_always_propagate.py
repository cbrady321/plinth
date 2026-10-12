"""always_propagate copies input files when stage does not write outputs."""

from __future__ import annotations

from pathlib import Path

from plinth.config import PipelineConfig
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import (
    experiment_dir,
    experiment_run_dir,
    prepare_work_dir,
    register_golden_stages,
    run_pipeline,
    tier_config_path,
)


def test_gt9_always_propagate_copies_data_files(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt9")
    run_pipeline("gt9", work)
    exp = experiment_dir(work, "gt9")
    touch_dirs = [p for p in exp.rglob("*golden_read_touch*") if p.is_dir()]
    assert touch_dirs
    data_files = list(touch_dirs[0].rglob("*.bin"))
    assert len(data_files) >= 1


def test_without_always_propagate_read_touch_does_not_copy(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt9")
    config = PipelineConfig.from_yaml(tier_config_path("gt9"))
    config.always_propagate = False
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt9_no_prop", work)
    pipeline.run(input_source=str(work / "data" / "dataset"))

    exp = experiment_run_dir(work, "golden_gt9_no_prop")
    touch_dirs = [p for p in exp.rglob("*golden_read_touch*") if p.is_dir()]
    assert touch_dirs
    assert not list(touch_dirs[0].rglob("*.bin"))
