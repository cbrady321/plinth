"""Resume idempotency contract helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plinth.blocks import Block
from plinth.dataset.manifest_rows import normalize_manifest_rows
from plinth.dataset.structures import MetadataLedger
from plinth.stage_directory import StageDirectoryManager


@dataclass(frozen=True)
class ManifestSnapshot:
    stage_name: str
    directory: Path
    rows: tuple[dict[str, Any], ...]


def _stage_name_from_directory(stage_dir: Path) -> str | None:
    ledger_path = stage_dir / "metadata_ledger.yaml"
    if ledger_path.exists():
        ledger = MetadataLedger.from_yaml(ledger_path)
        if ledger.entries:
            return ledger.entries[-1].stage_name
    manager = StageDirectoryManager(stage_dir.parent)
    for entry in manager.stage_directories:
        if entry.directory_path == stage_dir:
            return entry.stage_name
    return None


def collect_manifest_snapshots(experiment_dir: Path) -> dict[str, ManifestSnapshot]:
    manager = StageDirectoryManager(experiment_dir)
    snapshots: dict[str, ManifestSnapshot] = {}

    for stage_dir in manager.stage_directories:
        manifest_path = stage_dir.directory_path / "manifest.csv"
        if not manifest_path.exists():
            continue
        snapshots[stage_dir.stage_name] = ManifestSnapshot(
            stage_name=stage_dir.stage_name,
            directory=stage_dir.directory_path,
            rows=normalize_manifest_rows(manifest_path),
        )

    for manifest_path in experiment_dir.rglob("manifest.csv"):
        manifest_dir = manifest_path.parent
        stage_name = _stage_name_from_directory(manifest_dir)
        if stage_name is None or stage_name in snapshots:
            continue
        snapshots[stage_name] = ManifestSnapshot(
            stage_name=stage_name,
            directory=manifest_dir,
            rows=normalize_manifest_rows(manifest_path),
        )

    return snapshots


def upstream_stage_names(dag_root: Block, resume_stage_name: str) -> list[str]:
    ordered = dag_root.get_all_stage_names()
    if resume_stage_name not in ordered:
        raise ValueError(f"Stage '{resume_stage_name}' not found in DAG")
    index = ordered.index(resume_stage_name)
    return ordered[:index]


def assert_upstream_manifests_unchanged(
    before: dict[str, ManifestSnapshot],
    after: dict[str, ManifestSnapshot],
    upstream_names: list[str],
) -> None:
    missing = [name for name in upstream_names if name not in before or name not in after]
    if missing:
        raise AssertionError(f"Missing upstream manifest snapshots: {missing}")

    for name in upstream_names:
        if before[name].rows != after[name].rows:
            raise AssertionError(
                f"Upstream manifest changed for stage '{name}' after resume "
                f"({len(before[name].rows)} -> {len(after[name].rows)} rows)"
            )


def _ledger_entry_for_stage(stage_dir: Path, stage_name: str) -> Any | None:

    ledger_path = stage_dir / "metadata_ledger.yaml"
    if not ledger_path.exists():
        return None
    ledger = MetadataLedger.from_yaml(ledger_path)
    resolved_dir = stage_dir.resolve()
    for entry in reversed(ledger.entries):
        if entry.stage_name == stage_name and Path(entry.output_directory).resolve() == resolved_dir:
            return entry
    return None


def _find_stage_output_dir(experiment_dir: Path, stage_name: str) -> Path | None:
    manager = StageDirectoryManager(experiment_dir)
    for stage_dir in manager.stage_directories:
        if stage_dir.stage_name == stage_name:
            if _ledger_entry_for_stage(stage_dir.directory_path, stage_name):
                return stage_dir.directory_path

    for manifest_path in experiment_dir.rglob("manifest.csv"):
        manifest_dir = manifest_path.parent
        if _ledger_entry_for_stage(manifest_dir, stage_name):
            return manifest_dir
    return None


def validate_upstream_params_on_resume(
    experiment_dir: Path,
    dag_root: Block,
    resume_stage_name: str,
    params: dict[str, dict[str, Any]],
    always_propagate: bool,
) -> None:
    """Fail loud when upstream stage params changed since the preserved ledger was written."""
    from plinth.runtime.hashing import compute_params_hash

    upstream = upstream_stage_names(dag_root, resume_stage_name)
    for stage_name in upstream:
        stage_dir = _find_stage_output_dir(experiment_dir, stage_name)
        if stage_dir is None:
            continue

        entry = _ledger_entry_for_stage(stage_dir, stage_name)
        if entry is None:
            continue

        stage_params = dict(params.get(stage_name, {}))
        stage_params["_always_propagate"] = always_propagate
        expected_hash = compute_params_hash(stage_params)
        if entry.params_hash != expected_hash:
            raise ValueError(
                f"Resume rejected: upstream stage '{stage_name}' params changed "
                f"(resume policy): ledger params_hash does not match current config. "
                "Run full pipeline or start from an earlier stage."
            )


def resume_jsonpath_for_stage(config_dag: dict[str, Any], stage_name: str) -> str:
    root_name = config_dag["name"]

    def walk(node: dict[str, Any], prefix: str) -> str | None:
        if node.get("type") == "stage":
            if node["name"] == stage_name:
                return prefix
            return None
        for index, child in enumerate(node.get("children", [])):
            child_prefix = f"{prefix}.children[{index}]"
            found = walk(child, child_prefix)
            if found is not None:
                return found
        return None

    found = walk(config_dag, f"$.{root_name}")
    if found is None:
        raise ValueError(f"Stage '{stage_name}' not found in config DAG")
    return found
