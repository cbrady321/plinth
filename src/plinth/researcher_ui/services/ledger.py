"""Metadata ledger timeline and integrity checks."""

from __future__ import annotations

from pathlib import Path

from plinth.dataset.structures import MetadataLedger
from plinth.researcher_ui.models import LedgerEntryView, LedgerTimeline
from plinth.researcher_ui.services.run_index import list_stages, resolve_run_dir, resolve_stage_dir
from plinth.runtime.hash_chain_validator import validate_hash_chain


def _relative_stage_path(run_dir: Path, output_directory: str) -> str:
    try:
        return str(Path(output_directory).resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return Path(output_directory).name


def _load_best_cumulative_ledger(stages: list) -> tuple[MetadataLedger, Path | None]:
    best_ledger = MetadataLedger()
    best_path: Path | None = None
    for stage in stages:
        ledger_path = stage.directory_path / "metadata_ledger.yaml"
        if not ledger_path.exists():
            continue
        try:
            ledger = MetadataLedger.from_yaml(ledger_path)
        except Exception:
            continue
        if len(ledger.entries) >= len(best_ledger.entries):
            best_ledger = ledger
            best_path = ledger_path
    return best_ledger, best_path


def _validate_entry_chain(ledger: MetadataLedger) -> tuple[bool, str | None]:
    try:
        validate_hash_chain(ledger)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def load_ledger_timeline(runs_dir: Path, run_id: str) -> LedgerTimeline:
    run_dir = resolve_run_dir(runs_dir, run_id)
    if run_dir is None:
        return LedgerTimeline(
            run_id=run_id,
            entries=[],
            integrity_ok=False,
            error=f"Run not found: {run_id}",
        )

    stages = list_stages(run_dir)
    if not stages:
        return LedgerTimeline(
            run_id=run_id,
            entries=[],
            integrity_ok=True,
            error="No completed stages found for this run",
        )

    ledger, ledger_path = _load_best_cumulative_ledger(stages)
    if ledger_path is None:
        return LedgerTimeline(
            run_id=run_id,
            entries=[],
            integrity_ok=True,
            error=f"No metadata_ledger.yaml found under {run_dir}",
        )

    if not ledger.entries:
        return LedgerTimeline(
            run_id=run_id,
            entries=[],
            integrity_ok=True,
            error=f"Empty metadata_ledger.yaml at {ledger_path}",
        )

    integrity_ok, integrity_error = _validate_entry_chain(ledger)
    executed_paths = {
        _relative_stage_path(run_dir, entry.output_directory) for entry in ledger.entries
    }

    entries: list[LedgerEntryView] = []
    predecessor: str | None = None
    for entry in ledger.entries:
        entries.append(
            LedgerEntryView(
                stage_name=entry.stage_name,
                stage_path=_relative_stage_path(run_dir, entry.output_directory),
                timestamp=entry.timestamp,
                input_hash=entry.input_hash,
                output_hash=entry.output_hash,
                params_hash=entry.params_hash,
                params=dict(entry.params or {}),
                predecessor_hash=predecessor,
                arming_hash=entry.arming_hash or "",
                files_processed=entry.files_processed,
                duration_seconds=entry.duration_seconds,
                status="executed",
            )
        )
        predecessor = entry.output_hash or predecessor

    for stage in stages:
        rel = stage.directory_path.name
        if rel in executed_paths:
            continue
        if not (stage.directory_path / "metadata_ledger.yaml").exists():
            entries.append(
                LedgerEntryView(
                    stage_name=stage.stage_name,
                    stage_path=rel,
                    timestamp="",
                    input_hash="",
                    output_hash="",
                    params_hash="",
                    predecessor_hash=predecessor,
                    status="not_executed",
                )
            )

    return LedgerTimeline(
        run_id=run_id,
        entries=entries,
        integrity_ok=integrity_ok,
        integrity_error=integrity_error,
    )


def export_raw_ledger(runs_dir: Path, run_id: str, stage_path: str) -> Path | None:
    stage_dir = resolve_stage_dir(resolve_run_dir(runs_dir, run_id), stage_path)
    if stage_dir is None:
        return None
    ledger_path = stage_dir / "metadata_ledger.yaml"
    return ledger_path if ledger_path.exists() else None
