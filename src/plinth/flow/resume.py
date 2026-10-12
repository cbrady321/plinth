"""Resume gates for flow-control run identity."""

from __future__ import annotations

from pathlib import Path

from plinth.blocks import Block
from plinth.dataset.structures import MetadataLedger
from plinth.flow.identity import RunIdentity


def ledger_arming_hash(stage_dir: Path) -> str | None:
    ledger_path = stage_dir / "metadata_ledger.yaml"
    if not ledger_path.exists():
        return None
    ledger = MetadataLedger.from_yaml(ledger_path)
    if not ledger.entries:
        return None
    last = ledger.entries[-1]
    return getattr(last, "arming_hash", None) or None


def validate_arming_on_resume(
    experiment_dir: Path,
    dag_root: Block,
    resume_stage_name: str,
    run_identity: RunIdentity,
) -> None:
    """
    Fail loud when preserved upstream ledger arming_hash != current run identity.

    Mirrors validate_upstream_params_on_resume for arming drift.
    """
    from plinth.runtime.resume_policy import _find_stage_output_dir, upstream_stage_names

    expected = run_identity.arming_hash()
    for stage_name in upstream_stage_names(dag_root, resume_stage_name):
        stage_dir = _find_stage_output_dir(experiment_dir, stage_name)
        if stage_dir is None:
            continue
        recorded = ledger_arming_hash(stage_dir)
        if recorded is None:
            continue
        if recorded != expected:
            raise ValueError(
                f"Resume rejected: upstream stage '{stage_name}' arming changed "
                f"(flow resume gate): ledger arming_hash does not match current run. "
                "Run full pipeline or start from an earlier stage."
            )
