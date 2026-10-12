"""Capture the GT1 golden snapshot (and rebuild the shared golden input dataset).

Usage: ``python scripts/capture_golden_pipeline.py`` then ``python scripts/capture_golden_tiers.py``.
Regenerating snapshots changes test oracles — only do it for an intended, reviewed behaviour change.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from plinth.config import PipelineConfig
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import MetadataLedger

FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "golden_pipeline"
GOLDEN_ROOT = PROJECT_ROOT / "tests" / "golden" / "tiers" / "gt1"
INPUT_DATASET = FIXTURE_ROOT / "input" / "dataset"
EXPERIMENT_NAME = "golden_capture"


def _write_input_dataset() -> None:
    """Rebuild the input dataset. It carries no dataset_schema.yaml: golden runs use the default schema."""
    INPUT_DATASET.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "entity_id": "item_a",
            "batch": 1,
            "slot": "",
            "filename": "a.bin",
            "file_path": "files/a.bin",
        },
        {
            "entity_id": "item_b",
            "batch": 1,
            "slot": "",
            "filename": "b.bin",
            "file_path": "files/b.bin",
        },
    ]
    pd.DataFrame(rows).to_csv(INPUT_DATASET / "manifest.csv", index=False)
    files_dir = INPUT_DATASET / "files"
    files_dir.mkdir(exist_ok=True)
    for name in ("a.bin", "b.bin"):
        (files_dir / name).write_bytes(b"plinth-fixture-" + name.encode())


def _normalize_cell(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _normalize_manifest_row(row: dict) -> dict:
    normalized = dict(sorted((k, _normalize_cell(v)) for k, v in row.items()))
    media = MediaSpec()
    portable = media.portable_path(normalized)
    if portable is not None:
        normalized[media.path_column] = portable
    return normalized


def _normalize_manifest_rows(manifest_path: Path) -> list[dict]:
    df = pd.read_csv(manifest_path)
    df = df.sort_values(by=list(df.columns)).reset_index(drop=True)
    records = df.to_dict(orient="records")
    return [_normalize_manifest_row(row) for row in records]


def _ledger_chain(ledger_path: Path) -> list[dict]:
    ledger = MetadataLedger.from_yaml(ledger_path)
    chain: list[dict] = []
    for entry in ledger.entries:
        chain.append(
            {
                "stage_name": entry.stage_name,
                "input_hash": entry.input_hash,
                "output_hash": entry.output_hash,
                "params_hash": entry.params_hash,
                "files_processed": entry.files_processed,
            }
        )
    return chain


def _stage_directories(experiment_dir: Path) -> dict[str, list[str]]:
    if not experiment_dir.exists():
        return {}
    result: dict[str, list[str]] = {}
    for item in sorted(experiment_dir.iterdir()):
        if item.is_dir():
            result[item.name] = sorted(p.name for p in item.rglob("*") if p.is_file())
    return result


def _run_pipeline(project_root: Path) -> Path:
    from plinth.registry import StageRegistry
    from plinth.runtime.pipeline import Pipeline
    from tests.golden.golden_stages import register_all_golden_stages

    StageRegistry.clear()
    register_all_golden_stages()
    config = PipelineConfig.from_yaml(FIXTURE_ROOT / "config.yaml")
    pipeline = Pipeline(config, EXPERIMENT_NAME, project_root)
    input_dir = project_root / "data" / "dataset"
    return pipeline.run(input_source=str(input_dir))


def _find_stage_output(experiment_dir: Path) -> Path:
    candidates = [
        p.parent
        for p in experiment_dir.rglob("manifest.csv")
        if "allowlist_filter" in str(p)
    ]
    if not candidates:
        candidates = [p.parent for p in experiment_dir.rglob("manifest.csv")]
    if not candidates:
        raise RuntimeError(f"No manifest.csv under {experiment_dir}")
    return sorted(candidates, key=lambda p: len(p.parts))[-1]


def capture() -> None:
    work_root = FIXTURE_ROOT / "work"
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    dataset_dst = work_root / "data" / "dataset"
    _write_input_dataset()
    shutil.copytree(INPUT_DATASET, dataset_dst)

    final_dir = _run_pipeline(work_root)
    experiment_dir = work_root / "data" / "pipeline" / "runs" / EXPERIMENT_NAME

    stage_dir = _find_stage_output(experiment_dir)
    manifest_path = stage_dir / "manifest.csv"
    ledger_path = stage_dir / "metadata_ledger.yaml"
    schema_path = stage_dir / "dataset_schema.yaml"

    GOLDEN_ROOT.mkdir(parents=True, exist_ok=True)
    (GOLDEN_ROOT / "manifest_rows.json").write_text(
        json.dumps(_normalize_manifest_rows(manifest_path), indent=2, sort_keys=True)
    )
    (GOLDEN_ROOT / "ledger_chain.json").write_text(
        json.dumps(_ledger_chain(ledger_path), indent=2, sort_keys=True)
    )
    (GOLDEN_ROOT / "schema_snapshot.yaml").write_text(schema_path.read_text())
    (GOLDEN_ROOT / "stage_directories.json").write_text(
        json.dumps(_stage_directories(experiment_dir), indent=2, sort_keys=True)
    )
    meta = {
        "experiment_name": EXPERIMENT_NAME,
        "final_stage_dir": stage_dir.name,
        "capture_root": str(Path(final_dir).relative_to(PROJECT_ROOT)),
    }
    (GOLDEN_ROOT / "capture_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Golden snapshots written to {GOLDEN_ROOT}")


if __name__ == "__main__":
    capture()
