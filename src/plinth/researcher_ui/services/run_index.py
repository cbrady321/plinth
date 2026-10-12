"""Run discovery and indexing from on-disk layout."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from plinth.dataset.structures import MetadataLedger
from plinth.researcher_ui.models import RunDetail, RunSummary, StageInfo
from plinth.stage_directory import StageDataDirectory, StageDirectoryManager

STATUS_FILE = ".run_status.json"
CONFIG_SNAPSHOT = "pipeline_config.yaml"
ERROR_FILE = ".run_error.json"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _infer_status(run_dir: Path, stages: list[StageDataDirectory]) -> str:
    status_data = _read_json(run_dir / STATUS_FILE)
    if status_data and status_data.get("status"):
        return str(status_data["status"])

    error_data = _read_json(run_dir / ERROR_FILE)
    if error_data:
        return "failed"

    if not stages:
        return "unknown"

    incomplete = any(not (stage.directory_path / "manifest.csv").exists() for stage in stages)
    if incomplete and stages:
        # If the last stage lacks manifest, treat as in-progress or failed.
        last = stages[-1]
        if not (last.directory_path / "manifest.csv").exists():
            marker = run_dir / ".in_progress"
            return "in_progress" if marker.exists() else "failed"
    return "success"


def _pipeline_name(run_dir: Path) -> str | None:
    config_path = run_dir / CONFIG_SNAPSHOT
    if not config_path.exists():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return data.get("name")
    except (yaml.YAMLError, OSError):
        return None


def _duration_from_ledgers(stages: list[StageDataDirectory]) -> float | None:
    total = 0.0
    found = False
    for stage in stages:
        ledger = MetadataLedger.from_directory(stage.directory_path)
        for entry in ledger.entries:
            total += float(entry.duration_seconds or 0.0)
            found = True
    return total if found else None


def list_stages(run_dir: Path) -> list[StageDataDirectory]:
    manager = StageDirectoryManager(run_dir)
    ordered = list(manager.stage_directories)

    # Include nested stage directories that carry manifests but are not top-level numbered dirs.
    seen = {stage.directory_path.resolve() for stage in ordered}
    for manifest_path in sorted(run_dir.rglob("manifest.csv")):
        stage_dir = manifest_path.parent
        if stage_dir.resolve() in seen:
            continue
        parsed = StageDirectoryManager.parse_directory_name(stage_dir.name)
        if parsed:
            seq, name = parsed
            ordered.append(
                StageDataDirectory(sequence_number=int(seq), stage_name=name, directory_path=stage_dir)
            )
            seen.add(stage_dir.resolve())

    ordered.sort(key=lambda s: (s.sequence_number, str(s.directory_path)))
    return ordered


def _stage_info(stage: StageDataDirectory) -> StageInfo:
    stage_dir = stage.directory_path
    rel = stage_dir.name
    manifest = stage_dir / "manifest.csv"
    schema = _schema_path(stage_dir)
    ledger = stage_dir / "metadata_ledger.yaml"
    row_count = None
    if manifest.exists():
        try:
            import pandas as pd

            row_count = len(pd.read_csv(manifest))
        except Exception:
            row_count = None

    status: Literal["completed", "in_progress", "missing_artifacts"]
    if manifest.exists() and ledger.exists():
        status = "completed"
    elif manifest.exists() or ledger.exists():
        status = "in_progress"
    else:
        status = "missing_artifacts"

    return StageInfo(
        stage_path=rel,
        stage_name=stage.stage_name,
        sequence_number=stage.sequence_number,
        status=status,
        has_manifest=manifest.exists(),
        has_schema=schema is not None,
        has_ledger=ledger.exists(),
        row_count=row_count,
    )


def _schema_path(stage_dir: Path) -> Path | None:
    for name in ("dataset_schema.yaml", "schema.yaml"):
        candidate = stage_dir / name
        if candidate.exists():
            return candidate
    return None


def list_runs(
    runs_dir: Path,
    *,
    status_filter: str | None = None,
    sort: str = "recency",
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[RunSummary]:
    if not runs_dir.exists():
        return []

    summaries: list[RunSummary] = []
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        stages = list_stages(run_dir)
        status = _infer_status(run_dir, stages)
        if status_filter and status != status_filter:
            continue
        try:
            started_at = _iso(run_dir.stat().st_mtime)
        except OSError:
            started_at = None
        if from_date and started_at and started_at < from_date:
            continue
        if to_date and started_at and started_at > to_date:
            continue
        summaries.append(
            RunSummary(
                run_id=run_dir.name,
                status=status,  # type: ignore[arg-type]
                started_at=started_at,
                duration_seconds=_duration_from_ledgers(stages),
                stage_count=len(stages),
                pipeline_name=_pipeline_name(run_dir),
            )
        )

    if sort == "duration":
        summaries.sort(key=lambda r: r.duration_seconds or 0.0, reverse=True)
    elif sort == "status":
        summaries.sort(key=lambda r: r.status)
    else:
        summaries.sort(key=lambda r: r.started_at or "", reverse=True)
    return summaries


def resolve_run_dir(runs_dir: Path, run_id: str) -> Path | None:
    """The run directory named ``run_id`` directly under ``runs_dir``, or ``None``.

    ``run_id`` comes from the request URL, so it must be a plain directory name: anything that could
    walk out of ``runs_dir`` (separators, ``.``/``..``, a symlink pointing elsewhere) is refused.
    """
    if not run_id or run_id in {".", ".."} or any(sep in run_id for sep in ("/", "\\", "\x00")):
        return None
    root = runs_dir.resolve()
    candidate = (root / run_id).resolve()
    if candidate.parent != root or not candidate.is_dir():
        return None
    return candidate


def get_run(runs_dir: Path, run_id: str) -> RunDetail | None:
    run_dir = resolve_run_dir(runs_dir, run_id)
    if run_dir is None:
        return None
    stages = list_stages(run_dir)
    status = _infer_status(run_dir, stages)
    try:
        started_at = _iso(run_dir.stat().st_mtime)
    except OSError:
        started_at = None
    return RunDetail(
        run_id=run_id,
        status=status,
        started_at=started_at,
        duration_seconds=_duration_from_ledgers(stages),
        run_root=str(run_dir),
        stages=[_stage_info(stage) for stage in stages],
        pipeline_name=_pipeline_name(run_dir),
    )


def resolve_stage_dir(run_dir: Path | None, stage_path: str) -> Path | None:
    """The directory ``stage_path`` inside ``run_dir``, or ``None`` if it is missing or lies outside it."""
    if run_dir is None:
        return None
    run_resolved = run_dir.resolve()
    candidate = (run_resolved / stage_path).resolve()
    if not candidate.is_relative_to(run_resolved) or not candidate.is_dir():
        return None
    return candidate
