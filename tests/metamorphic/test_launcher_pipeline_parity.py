"""ExperimentLauncher must match Pipeline for validated runs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from plinth.config import PipelineConfig
from plinth.experiment_launcher import ExperimentLauncher
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import prepare_work_dir, register_golden_stages, tier_config_path


@pytest.mark.metamorphic
def test_launcher_run_matches_pipeline_output_dir(tmp_path: Path) -> None:
    work_pipeline = prepare_work_dir(tmp_path / "pipeline", "gt2")
    work_launcher = prepare_work_dir(tmp_path / "launcher", "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()

    pipeline = Pipeline(config, "golden_gt2", work_pipeline)
    pipeline_out = Path(pipeline.run(input_source=str(work_pipeline / "data" / "dataset")))

    launcher = ExperimentLauncher(work_launcher)
    launcher_out = launcher.run(
        config,
        "golden_gt2",
        input_source=str(work_launcher / "data" / "dataset"),
    )

    pipeline_manifest = pd.read_csv(pipeline_out / "manifest.csv")
    launcher_manifest = pd.read_csv(launcher_out.output_dir / "manifest.csv")
    compare_cols = [c for c in pipeline_manifest.columns if c != "file_path"]
    pd.testing.assert_frame_equal(
        pipeline_manifest[compare_cols],
        launcher_manifest[compare_cols],
    )


@pytest.mark.metamorphic
def test_launcher_validate_rejects_unknown_stage() -> None:
    config = PipelineConfig(
        name="bad",
        version="1",
        dag={
            "type": "sequential",
            "name": "root",
            "children": [{"type": "stage", "name": "not_a_real_stage"}],
        },
        params={},
    )
    launcher = ExperimentLauncher(Path("."))
    result = launcher.validate(config)
    assert not result.ok
    assert any("not_a_real_stage" in err for err in result.errors)

    with pytest.raises(ValueError, match="Invalid pipeline config"):
        launcher.run(config, "bad_exp")
