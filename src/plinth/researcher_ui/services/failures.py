"""Failure triage from run metadata and stage logs."""

from __future__ import annotations

import json
from pathlib import Path

from plinth.researcher_ui.models import FailureReport, RowFailure
from plinth.researcher_ui.services.run_index import ERROR_FILE, STATUS_FILE, list_stages, resolve_run_dir


def _tail_file(path: Path, lines: int = 50) -> str | None:
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except OSError:
        return None


def _find_log_file(stage_dir: Path) -> Path | None:
    for name in ("stage.log", "run.log", "error.log", "stderr.log"):
        candidate = stage_dir / name
        if candidate.exists():
            return candidate
    logs_dir = stage_dir / "logs"
    if logs_dir.is_dir():
        log_files = sorted(logs_dir.glob("*.log"))
        if log_files:
            return log_files[-1]
    return None


def load_failure_report(runs_dir: Path, run_id: str) -> FailureReport:
    run_dir = resolve_run_dir(runs_dir, run_id)
    if run_dir is None:
        return FailureReport(run_id=run_id, status="unknown", error=f"Run not found: {run_id}")

    status_data = None
    status_path = run_dir / STATUS_FILE
    if status_path.exists():
        try:
            status_data = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status_data = None

    error_data = None
    error_path = run_dir / ERROR_FILE
    if error_path.exists():
        try:
            error_data = json.loads(error_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            error_data = None

    stages = list_stages(run_dir)
    status = (status_data or {}).get("status") or ("failed" if error_data else "unknown")

    first_failing_stage = (error_data or {}).get("stage_path") or (status_data or {}).get("failed_stage")
    stage_error = (error_data or {}).get("message") or (status_data or {}).get("error")
    stack_summary = (error_data or {}).get("stack_summary")
    error_kind = (error_data or {}).get("kind", "unknown")

    row_failures: list[RowFailure] = []
    cancelled_branches: list[str] = []
    for item in (error_data or {}).get("row_failures", []):
        row_failures.append(
            RowFailure(
                entity_id=item.get("entity_id"),
                row_index=item.get("row_index"),
                stage_path=item.get("stage_path", ""),
                error_message=item.get("error_message", ""),
            )
        )

    for branch in (error_data or {}).get("cancelled_branches", []):
        cancelled_branches.append(str(branch))

    if not first_failing_stage and stages:
        for stage in reversed(stages):
            if not (stage.directory_path / "manifest.csv").exists():
                first_failing_stage = stage.directory_path.name
                if not stage_error:
                    stage_error = "Stage completed without manifest.csv"
                break

    log_tail = None
    if first_failing_stage:
        stage_dir = run_dir / first_failing_stage
        if stage_dir.is_dir():
            log_file = _find_log_file(stage_dir)
            if log_file:
                log_tail = _tail_file(log_file)

    if error_kind not in ("stage_logic", "infrastructure", "unknown"):
        error_kind = "unknown"

    return FailureReport(
        run_id=run_id,
        status=status,
        first_failing_stage=first_failing_stage,
        stage_error=stage_error,
        stack_summary=stack_summary,
        row_failures=row_failures,
        cancelled_branches=cancelled_branches,
        log_tail=log_tail,
        error_kind=error_kind,  # type: ignore[arg-type]
    )
