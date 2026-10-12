"""Resume and re-run recovery integration gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.dataset.manifest_rows import normalize_manifest_rows
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import (
    experiment_dir,
    experiment_run_dir,
    find_final_stage_dir,
    prepare_work_dir,
    register_golden_stages,
    run_pipeline,
    tier_config_path,
)


def test_resume_from_nonexistent_stage_fails_loudly(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(ValueError, match="not found in DAG"):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="nonexistent_stage_xyz",
        )


def test_resume_missing_upstream_dir_fails_loudly(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    run_pipeline("gt2", work, end_at_stage="allowlist_filter")
    exp = experiment_dir(work, "gt2")
    filter_dirs = [p for p in exp.iterdir() if p.is_dir() and "allowlist_filter" in p.name]
    assert filter_dirs
    import shutil

    shutil.rmtree(filter_dirs[0])

    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(FileNotFoundError, match="output directory not found"):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="tag_category",
        )


def test_resume_with_truncated_upstream_ledger_fails(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    run_pipeline("gt2", work, end_at_stage="tag_category")
    exp = experiment_dir(work, "gt2")
    filter_dirs = [p for p in exp.iterdir() if p.is_dir() and "allowlist_filter" in p.name]
    ledger_path = filter_dirs[0] / "metadata_ledger.yaml"
    ledger_path.write_text("# truncated\nentries:\n  - stage_name: x\n    input_hash: ")

    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises((ValueError, KeyError, TypeError)):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="golden_filter_b",
        )


def test_full_re_run_on_same_experiment_is_idempotent(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    register_golden_stages()
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    dataset = str(work / "data" / "dataset")

    pipeline = Pipeline(config, "golden_gt2", work)
    pipeline.run(input_source=dataset)
    first = normalize_manifest_rows(find_final_stage_dir(experiment_dir(work, "gt2")) / "manifest.csv")

    pipeline.run(input_source=dataset)
    second = normalize_manifest_rows(find_final_stage_dir(experiment_dir(work, "gt2")) / "manifest.csv")

    assert first == second


def test_failed_run_resume_completes(tmp_path: Path, isolated_registry: None) -> None:
    class _FailStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
            raise RuntimeError("intentional failure")

    class _OkStage(BaseStage):
        def get_intent(self) -> StageIntent:
            return StageIntent(reads_files=False, modifies_files=False)

        def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
            return StageOutcome.update(recovered=True)

    StageRegistry.register("recovery_fail")(_FailStage)
    StageRegistry.register("recovery_ok")(_OkStage)

    work = prepare_work_dir(tmp_path)
    dataset = work / "data" / "dataset"
    config = PipelineConfig(
        name="recovery",
        version="1",
        input_source="dataset",
        dag={
            "type": "sequential",
            "name": "root",
            "children": [
                {"type": "stage", "name": "recovery_fail"},
                {"type": "stage", "name": "recovery_ok"},
            ],
        },
        params={"recovery_fail": {}, "recovery_ok": {}},
    )

    pipeline = Pipeline(config, "recovery_exp", work)
    with pytest.raises((RuntimeError, ValueError), match="intentional failure|Row failure"):
        pipeline.run(input_source=str(dataset))

    StageRegistry.register("recovery_fail")(_OkStage)
    pipeline_resume = Pipeline(config, "recovery_exp", work)
    pipeline_resume.run(input_source=str(dataset), start_from_stage="recovery_fail")

    final_manifest = normalize_manifest_rows(
        find_final_stage_dir(experiment_run_dir(work, "recovery_exp")) / "manifest.csv"
    )
    assert final_manifest


def test_resume_rejects_upstream_param_change(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    run_pipeline("gt2", work)

    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config.params["allowlist_filter"]["allow"] = ["b.bin"]
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)

    with pytest.raises(ValueError, match="params changed"):
        pipeline.run(
            input_source=str(work / "data" / "dataset"),
            start_from_stage="tag_category",
        )


def test_resume_allows_target_stage_param_change(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    full_out = run_pipeline("gt2", work)
    full_manifest = normalize_manifest_rows(full_out / "manifest.csv")

    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config.params["tag_category"]["default_category"] = "changed_category"
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt2", work)
    pipeline.run(
        input_source=str(work / "data" / "dataset"),
        start_from_stage="tag_category",
    )

    resume_manifest = normalize_manifest_rows(
        find_final_stage_dir(experiment_dir(work, "gt2")) / "manifest.csv"
    )
    assert resume_manifest != full_manifest
