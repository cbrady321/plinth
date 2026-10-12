"""Engine-owned metadata ledger writes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from plinth.dataset.structures import MetadataLedger, MetadataLedgerAggregation, MetadataLedgerEntry


class LedgerWriter:
    def append_entry(
        self,
        ledger: MetadataLedger,
        *,
        stage_name: str,
        function_name: str,
        input_directory: str,
        output_directory: str,
        input_hash: str,
        output_hash: str,
        params_hash: str,
        params: dict[str, Any],
        files_processed: int,
        duration_seconds: float,
        arming_hash: str = "",
    ) -> MetadataLedgerEntry:
        entry = MetadataLedgerEntry(
            stage_name=stage_name,
            timestamp=datetime.now().isoformat(),
            function_name=function_name,
            input_directory=input_directory,
            output_directory=output_directory,
            input_hash=input_hash,
            output_hash=output_hash,
            params_hash=params_hash,
            params=params,
            files_processed=files_processed,
            duration_seconds=duration_seconds,
            arming_hash=arming_hash,
        )
        ledger.append(entry)
        return entry

    def record_aggregation(
        self,
        ledger: MetadataLedger,
        *,
        block_name: str,
        input_hashes: list[str],
        output_hash: str,
    ) -> MetadataLedgerAggregation:
        aggregation = MetadataLedgerAggregation(
            block_name=block_name,
            input_hashes=list(input_hashes),
            output_hash=output_hash,
        )
        ledger.record_aggregation(aggregation)
        return aggregation

    def write(self, ledger: MetadataLedger, output_dir: Path) -> None:
        ledger.to_yaml(output_dir / "metadata_ledger.yaml")
