"""Runtime verification of exceptional stage obligations."""

from __future__ import annotations

from plinth.address.resolver import NodeAddressResolver
from plinth.context import StageContext
from plinth.dataset.structures import MetadataLedger
from plinth.registry import ExceptionalMetadata, StageRegistry


class ExceptionalObligationError(ValueError):
    def __init__(self, obligation: str, stage_name: str, detail: str) -> None:
        super().__init__(f"Exceptional obligation {obligation!r} failed for stage {stage_name!r}: {detail}")
        self.obligation = obligation
        self.stage_name = stage_name


def verify_exceptional_obligations(
    stage_name: str,
    context: StageContext,
    *,
    input_ledger_entries: int,
) -> None:
    metadata = StageRegistry.get_exceptional_metadata(stage_name) or ExceptionalMetadata()
    obligations = metadata.obligations
    output_dir = context.get_output_dir()

    if obligations.records_ledger:
        output_ledger = MetadataLedger.from_directory(output_dir)
        if not output_ledger.entries:
            raise ExceptionalObligationError(
                "records_ledger",
                stage_name,
                "output metadata_ledger.yaml has no entries",
            )
        if output_ledger.entries[-1].stage_name != stage_name:
            raise ExceptionalObligationError(
                "records_ledger",
                stage_name,
                f"latest ledger entry stage {output_ledger.entries[-1].stage_name!r} != {stage_name!r}",
            )
        if len(output_ledger.entries) <= input_ledger_entries:
            raise ExceptionalObligationError(
                "records_ledger",
                stage_name,
                "output ledger did not append a new entry",
            )

    if obligations.hands_off_manifest:
        manifest_path = output_dir / "manifest.csv"
        if not manifest_path.exists():
            raise ExceptionalObligationError(
                "hands_off_manifest",
                stage_name,
                f"missing manifest.csv in {output_dir}",
            )

    if obligations.uses_resolver_address:
        parsed = NodeAddressResolver().match_directory(output_dir.name)
        if parsed is None:
            raise ExceptionalObligationError(
                "uses_resolver_address",
                stage_name,
                f"output directory name {output_dir.name!r} is not resolver-parseable",
            )
