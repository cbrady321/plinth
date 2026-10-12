"""Shared helpers for golden-tier pipeline runs in tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from plinth.config import PipelineConfig
from plinth.registry import StageRegistry
from tests.golden.tier_catalog import resume_stage_for_tier

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "golden_pipeline"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def prepare_work_dir(tmp_path: Path, tier: str = "") -> Path:
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)
    dataset_src = FIXTURE_ROOT / "input" / "dataset"
    shutil.copytree(dataset_src, work / "data" / "dataset")
    return work


def register_golden_stages() -> None:
    StageRegistry.clear()
    from tests.golden.golden_stages import register_all_golden_stages

    register_all_golden_stages()


def run_pipeline(
    tier: str,
    work_root: Path,
    *,
    start_from_stage: str | None = None,
    end_at_stage: str | None = None,
) -> Path:
    from plinth.runtime.pipeline import Pipeline

    register_golden_stages()
    config_path = tier_config_path(tier)
    config = PipelineConfig.from_yaml(config_path)
    experiment = f"golden_{tier}"
    pipeline = Pipeline(config, experiment, work_root)
    input_dir = work_root / "data" / "dataset"
    resume_stage = resume_stage_for_tier(tier)
    if resume_stage and start_from_stage is None and end_at_stage is None:
        pipeline.run(input_source=str(input_dir))
        return pipeline.run(input_source=str(input_dir), start_from_stage=resume_stage)
    return pipeline.run(
        input_source=str(input_dir),
        start_from_stage=start_from_stage,
        end_at_stage=end_at_stage,
    )


def run_via_launcher(
    tier: str,
    work_root: Path,
    experiment_name: str | None = None,
    *,
    start_from_stage: str | None = None,
) -> Path:
    from plinth.experiment_launcher import ExperimentLauncher

    register_golden_stages()
    config = PipelineConfig.from_yaml(tier_config_path(tier))
    experiment = experiment_name or f"golden_{tier}"
    launcher = ExperimentLauncher(work_root)
    resume_stage = resume_stage_for_tier(tier)
    if resume_stage and start_from_stage is None:
        launcher.run(config, experiment, input_source=str(work_root / "data" / "dataset"))
        result = launcher.run(
            config,
            experiment,
            input_source=str(work_root / "data" / "dataset"),
            start_from_stage=resume_stage,
        )
        return result.output_dir
    result = launcher.run(
        config,
        experiment,
        input_source=str(work_root / "data" / "dataset"),
        start_from_stage=start_from_stage,
    )
    return result.output_dir


def tier_config_path(tier: str) -> Path:
    if tier == "gt1":
        return FIXTURE_ROOT / "config.yaml"
    return FIXTURE_ROOT / "tiers" / tier / "config.yaml"


def experiment_run_dir(work_root: Path, experiment_name: str) -> Path:
    return work_root / "data" / "pipeline" / "runs" / experiment_name


def experiment_dir(work_root: Path, tier: str) -> Path:
    return experiment_run_dir(work_root, f"golden_{tier}")


def find_final_stage_dir(experiment: Path, snapshot_root: Path | None = None) -> Path:
    if snapshot_root and (snapshot_root / "capture_meta.json").exists():
        meta = json.loads((snapshot_root / "capture_meta.json").read_text())
        final_dir = meta.get("final_stage_dir")
        if final_dir:
            candidate = experiment / final_dir
            if (candidate / "manifest.csv").exists():
                return candidate
    manifests = list(experiment.rglob("manifest.csv"))
    if not manifests:
        raise RuntimeError(f"No manifest.csv under {experiment}")
    return sorted(manifests, key=lambda p: p.parent.name)[-1].parent


def normalize_manifest_rows(manifest_path: Path) -> tuple[dict, ...]:
    from plinth.dataset.manifest_rows import normalize_manifest_rows as _norm

    return _norm(manifest_path)
