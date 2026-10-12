"""Golden pipeline equivalence tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from plinth.config import PipelineConfig
from plinth.dataset.structures import MetadataLedger
from plinth.registry import StageRegistry
from plinth.runtime.hash_chain_validator import validate_hash_chain
from scripts.capture_golden_pipeline import _normalize_manifest_row
from tests.golden.run_harness import experiment_run_dir

FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "golden_pipeline"
TIERS_ROOT = PROJECT_ROOT / "tests" / "golden" / "tiers"

GOLDEN_TIERS = {
    "gt1": {
        "config": FIXTURE_ROOT / "config.yaml",
        "snapshots": TIERS_ROOT / "gt1",
        "experiment": "golden_gt1",
    },
    "gt2": {
        "config": FIXTURE_ROOT / "tiers" / "gt2" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt2",
        "experiment": "golden_gt2",
    },
    "gt3": {
        "config": FIXTURE_ROOT / "tiers" / "gt3" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt3",
        "experiment": "golden_gt3",
    },
    "gt4": {
        "config": FIXTURE_ROOT / "tiers" / "gt4" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt4",
        "experiment": "golden_gt4",
    },
    "gt5": {
        "config": FIXTURE_ROOT / "tiers" / "gt5" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt5",
        "experiment": "golden_gt5",
    },
    "gt6": {
        "config": FIXTURE_ROOT / "tiers" / "gt6" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt6",
        "experiment": "golden_gt6",
    },
    "gt7": {
        "config": FIXTURE_ROOT / "tiers" / "gt7" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt7",
        "experiment": "golden_gt7",
    },
    "gt8": {
        "config": FIXTURE_ROOT / "tiers" / "gt8" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt8",
        "experiment": "golden_gt8",
        "resume_stage": "tag_category",
    },
    "gt9": {
        "config": FIXTURE_ROOT / "tiers" / "gt9" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt9",
        "experiment": "golden_gt9",
    },
    "gt10": {
        "config": FIXTURE_ROOT / "tiers" / "gt10" / "config.yaml",
        "snapshots": TIERS_ROOT / "gt10",
        "experiment": "golden_gt10",
    },
}



def _normalize_manifest_rows(manifest_path: Path) -> list[dict]:
    df = pd.read_csv(manifest_path)
    df = df.sort_values(by=list(df.columns)).reset_index(drop=True)
    records = df.to_dict(orient="records")
    return [_normalize_manifest_row(row) for row in records]


def _ledger_chain(ledger_path: Path) -> list[dict]:
    ledger = MetadataLedger.from_yaml(ledger_path)
    return [
        {
            "stage_name": entry.stage_name,
            "input_hash": entry.input_hash,
            "output_hash": entry.output_hash,
            "params_hash": entry.params_hash,
            "files_processed": entry.files_processed,
        }
        for entry in ledger.entries
    ]


def _stage_directories(experiment_dir: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in sorted(experiment_dir.iterdir()):
        if item.is_dir():
            result[item.name] = sorted(p.name for p in item.rglob("*") if p.is_file())
    return result


def _snapshot_root(tier: str) -> Path:
    spec = GOLDEN_TIERS[tier]
    if spec["snapshots"].exists():
        return spec["snapshots"]
    raise FileNotFoundError(f"No snapshots for tier {tier}")


def _load_golden_stages() -> None:
    import importlib.util

    path = Path(__file__).resolve().parent / "golden_stages.py"
    spec = importlib.util.spec_from_file_location("golden_stages", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


@pytest.fixture(autouse=True)
def _restore_registry_after_each_tier() -> Iterator[None]:
    # Tiers re-register the golden stages; leave the registry as the next test expects it.
    tables = ("_stages", "_modes", "_exceptional_metadata")
    before = {table: dict(getattr(StageRegistry, table)) for table in tables}
    yield
    for table, entries in before.items():
        current = getattr(StageRegistry, table)
        current.clear()
        current.update(entries)


def _run_golden_pipeline(tier: str, work_root: Path) -> Path:
    from plinth.runtime.pipeline import Pipeline

    StageRegistry.clear()
    from tests.golden.golden_stages import register_all_golden_stages

    register_all_golden_stages()
    spec = GOLDEN_TIERS[tier]
    config = PipelineConfig.from_yaml(spec["config"])
    pipeline = Pipeline(config, spec["experiment"], work_root)
    input_dir = work_root / "data" / "dataset"
    resume_stage = spec.get("resume_stage")
    if resume_stage:
        pipeline.run(input_source=str(input_dir))
        return pipeline.run(input_source=str(input_dir), start_from_stage=resume_stage)
    return pipeline.run(input_source=str(input_dir))


def _find_stage_output(experiment_dir: Path, snapshot_root: Path) -> Path:
    meta_path = snapshot_root / "capture_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        final_dir = meta.get("final_stage_dir")
        if final_dir:
            candidate = experiment_dir / final_dir
            if (candidate / "manifest.csv").exists():
                return candidate
    manifests = list(experiment_dir.rglob("manifest.csv"))
    if not manifests:
        raise RuntimeError(f"No manifest.csv under {experiment_dir}")
    return sorted(manifests, key=lambda p: p.parent.name)[-1].parent


@pytest.fixture
def golden_work_dir(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    dataset_src = FIXTURE_ROOT / "input" / "dataset"
    shutil.copytree(dataset_src, work / "data" / "dataset")
    return work


@pytest.mark.parametrize("tier", ["gt1", "gt2", "gt3", "gt4", "gt5", "gt6", "gt7", "gt8", "gt9", "gt10"])
def test_golden_tier_equivalence(golden_work_dir: Path, tier: str) -> None:
    snapshot_root = _snapshot_root(tier)
    if not (snapshot_root / "manifest_rows.json").exists():
        pytest.skip(f"Golden tier {tier} snapshots missing — run scripts/capture_golden_tiers.py")

    _run_golden_pipeline(tier, golden_work_dir)
    experiment_dir = experiment_run_dir(golden_work_dir, GOLDEN_TIERS[tier]["experiment"])
    stage_dir = _find_stage_output(experiment_dir, snapshot_root)

    expected_manifest = [
        _normalize_manifest_row(row)
        for row in json.loads((snapshot_root / "manifest_rows.json").read_text())
    ]
    expected_ledger = json.loads((snapshot_root / "ledger_chain.json").read_text())
    expected_schema = (snapshot_root / "schema_snapshot.yaml").read_text()
    expected_dirs = json.loads((snapshot_root / "stage_directories.json").read_text())

    actual_manifest = _normalize_manifest_rows(stage_dir / "manifest.csv")
    actual_ledger = _ledger_chain(stage_dir / "metadata_ledger.yaml")
    actual_schema_text = (stage_dir / "dataset_schema.yaml").read_text()
    actual_dirs = _stage_directories(experiment_dir)
    ledger = MetadataLedger.from_yaml(stage_dir / "metadata_ledger.yaml")

    validate_hash_chain(ledger)

    assert actual_manifest == expected_manifest
    assert actual_ledger == expected_ledger
    assert actual_schema_text == expected_schema
    assert actual_dirs == expected_dirs


@pytest.mark.parametrize("tier", ["gt2", "gt3", "gt4"])
def test_provenance_entry_count_matches_stage_count(golden_work_dir: Path, tier: str) -> None:
    snapshot_root = _snapshot_root(tier)
    if not (snapshot_root / "ledger_chain.json").exists():
        pytest.skip(f"Golden tier {tier} snapshots missing")

    _run_golden_pipeline(tier, golden_work_dir)
    experiment_dir = experiment_run_dir(golden_work_dir, GOLDEN_TIERS[tier]["experiment"])
    stage_dir = _find_stage_output(experiment_dir, snapshot_root)
    ledger = MetadataLedger.from_yaml(stage_dir / "metadata_ledger.yaml")
    expected_count = len(json.loads((snapshot_root / "ledger_chain.json").read_text()))
    assert len(ledger.entries) == expected_count
    assert expected_count >= 1


def test_golden_pipeline_equivalence(golden_work_dir: Path) -> None:
    test_golden_tier_equivalence(golden_work_dir, "gt1")


@pytest.mark.parametrize("tier", ["gt1", "gt2", "gt3", "gt4", "gt5", "gt6", "gt7", "gt8", "gt9", "gt10"])
def test_golden_ledger_hashes_cover_row_data(tier: str) -> None:
    """No recorded stage hashes to the empty-input digest: every directory holds at least a manifest."""
    ledger = json.loads((_snapshot_root(tier) / "ledger_chain.json").read_text())
    empty = hashlib.sha256(b"").hexdigest()
    assert all(entry["input_hash"] != empty and entry["output_hash"] != empty for entry in ledger)
