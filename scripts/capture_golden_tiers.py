"""Capture golden tier snapshots GT2–GT10 (GT1 is captured by ``capture_golden_pipeline.py``)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from plinth.config import PipelineConfig  # noqa: E402
from scripts.capture_golden_pipeline import (  # noqa: E402
    FIXTURE_ROOT,
    INPUT_DATASET,
    _ledger_chain,
    _normalize_manifest_rows,
    _stage_directories,
    _write_input_dataset,
)

GOLDEN_TIERS_ROOT = PROJECT_ROOT / "tests" / "golden" / "tiers"


def _run_tier(tier: str, config_path: Path, work_root: Path, resume_stage: str | None = None) -> Path:
    from plinth.registry import StageRegistry
    from plinth.runtime.pipeline import Pipeline
    from tests.golden.golden_stages import register_all_golden_stages

    StageRegistry.clear()
    register_all_golden_stages()
    config = PipelineConfig.from_yaml(config_path)
    experiment = f"golden_{tier}"
    pipeline = Pipeline(config, experiment, work_root)
    input_dir = work_root / "data" / "dataset"
    if resume_stage:
        pipeline.run(input_source=str(input_dir))
        return pipeline.run(input_source=str(input_dir), start_from_stage=resume_stage)
    return pipeline.run(input_source=str(input_dir))


def _find_final_manifest_parent(experiment_dir: Path) -> Path:
    manifests = list(experiment_dir.rglob("manifest.csv"))
    if not manifests:
        raise RuntimeError(f"No manifest under {experiment_dir}")
    return sorted(manifests, key=lambda p: p.parent.name)[-1].parent


def capture_tier(tier: str, config_path: Path, resume_stage: str | None = None) -> None:
    work_root = FIXTURE_ROOT / "work" / tier
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    dataset_dst = work_root / "data" / "dataset"
    _write_input_dataset()
    shutil.copytree(INPUT_DATASET, dataset_dst)

    _run_tier(tier, config_path, work_root, resume_stage=resume_stage)
    experiment_dir = work_root / "data" / "pipeline" / "runs" / f"golden_{tier}"
    stage_dir = _find_final_manifest_parent(experiment_dir)

    tier_snapshot_dir = GOLDEN_TIERS_ROOT / tier
    tier_snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = stage_dir / "manifest.csv"
    ledger_path = stage_dir / "metadata_ledger.yaml"
    schema_path = stage_dir / "dataset_schema.yaml"

    (tier_snapshot_dir / "manifest_rows.json").write_text(
        json.dumps(_normalize_manifest_rows(manifest_path), indent=2, sort_keys=True)
    )
    (tier_snapshot_dir / "ledger_chain.json").write_text(
        json.dumps(_ledger_chain(ledger_path), indent=2, sort_keys=True)
    )
    (tier_snapshot_dir / "schema_snapshot.yaml").write_text(schema_path.read_text())
    (tier_snapshot_dir / "stage_directories.json").write_text(
        json.dumps(_stage_directories(experiment_dir), indent=2, sort_keys=True)
    )
    meta = {
        "tier": tier,
        "final_stage_dir": stage_dir.name,
        "stage_count": len(_ledger_chain(ledger_path)),
    }
    (tier_snapshot_dir / "capture_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Captured {tier} -> {tier_snapshot_dir}")


def main() -> None:
    tiers = {
        "gt2": (FIXTURE_ROOT / "tiers" / "gt2" / "config.yaml", None),
        "gt3": (FIXTURE_ROOT / "tiers" / "gt3" / "config.yaml", None),
        "gt4": (FIXTURE_ROOT / "tiers" / "gt4" / "config.yaml", None),
        "gt5": (FIXTURE_ROOT / "tiers" / "gt5" / "config.yaml", None),
        "gt6": (FIXTURE_ROOT / "tiers" / "gt6" / "config.yaml", None),
        "gt7": (FIXTURE_ROOT / "tiers" / "gt7" / "config.yaml", None),
        "gt8": (FIXTURE_ROOT / "tiers" / "gt8" / "config.yaml", "tag_category"),
        "gt9": (FIXTURE_ROOT / "tiers" / "gt9" / "config.yaml", None),
        "gt10": (FIXTURE_ROOT / "tiers" / "gt10" / "config.yaml", None),
    }
    for tier, (config_path, resume_stage) in tiers.items():
        capture_tier(tier, config_path, resume_stage=resume_stage)


if __name__ == "__main__":
    main()
