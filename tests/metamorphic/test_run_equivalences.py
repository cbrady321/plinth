"""Metamorphic run equivalences: full run ≡ resume-from-k."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.config import PipelineConfig
from plinth.dataset.manifest_rows import normalize_manifest_rows
from plinth.dataset.structures import MetadataLedger
from plinth.experiment_launcher import ExperimentLauncher
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import (
    experiment_dir,
    find_final_stage_dir,
    prepare_work_dir,
    register_golden_stages,
    run_pipeline,
    tier_config_path,
)
from tests.golden.tier_catalog import ALL_GOLDEN_TIERS


@pytest.mark.metamorphic
@pytest.mark.parametrize("tier", list(ALL_GOLDEN_TIERS))
def test_full_run_equals_resume_from_each_stage(tmp_path: Path, tier: str) -> None:
    work_full = prepare_work_dir(tmp_path / "full", tier)
    run_pipeline(tier, work_full)
    full_exp = experiment_dir(work_full, tier)
    full_manifest = normalize_manifest_rows(find_final_stage_dir(full_exp) / "manifest.csv")

    config = PipelineConfig.from_yaml(tier_config_path(tier))
    dag_root = config.build_dag()
    stage_names = dag_root.get_all_stage_names()

    for resume_stage in stage_names:
        work_resume = prepare_work_dir(tmp_path / f"resume_{tier}_{resume_stage}", tier)
        run_pipeline(tier, work_resume)
        register_golden_stages()
        pipeline = Pipeline(config, f"golden_{tier}", work_resume)
        pipeline.run(
            input_source=str(work_resume / "data" / "dataset"),
            start_from_stage=resume_stage,
        )
        resume_exp = experiment_dir(work_resume, tier)
        resume_manifest = normalize_manifest_rows(find_final_stage_dir(resume_exp) / "manifest.csv")
        assert resume_manifest == full_manifest, f"{tier} resume from {resume_stage} diverged"


@pytest.mark.metamorphic
@pytest.mark.parametrize("tier", list(ALL_GOLDEN_TIERS))
def test_ledger_hashes_are_deterministic_across_runs_and_locations(tmp_path: Path, tier: str) -> None:
    ledgers = []
    for location in ("first", "second/nested"):
        work = prepare_work_dir(tmp_path / location, tier)
        run_pipeline(tier, work)
        final_dir = find_final_stage_dir(experiment_dir(work, tier))
        ledgers.append(MetadataLedger.from_directory(final_dir))
    first, second = ledgers
    assert [(e.stage_name, e.input_hash, e.output_hash) for e in first.entries] == [
        (e.stage_name, e.input_hash, e.output_hash) for e in second.entries
    ]
    assert first.aggregations == second.aggregations


@pytest.mark.metamorphic
def test_pipeline_and_launcher_reject_invalid_resume_stage(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)
    launcher = ExperimentLauncher(work)

    with pytest.raises(ValueError, match="not found in DAG"):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="nonexistent_stage_xyz",
        )

    with pytest.raises(ValueError, match="not found in DAG"):
        launcher.run(
            config,
            "golden_gt2_launcher",
            input_source=str(work / "data" / "dataset"),
            start_from_stage="nonexistent_stage_xyz",
        )
