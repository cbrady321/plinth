"""Mandatory ledger hash-chain validation."""

from __future__ import annotations

from plinth.dataset.structures import MetadataLedger, MetadataLedgerAggregation


def _aggregated_from(
    output_hash: str, aggregations: list[MetadataLedgerAggregation], produced: set[str]
) -> set[str]:
    """Hashes an aggregation output was merged from, transitively, if every input is ``produced``.

    Empty when no recorded aggregation explains ``output_hash`` from directories already seen.
    """
    sources: set[str] = set()
    pending = [output_hash]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        aggregation = next((a for a in aggregations if a.output_hash == current and a.input_hashes), None)
        if aggregation is None:
            if current not in produced:
                return set()
            sources.add(current)
            continue
        sources.update(aggregation.input_hashes)
        pending.extend(aggregation.input_hashes)
    return sources


def validate_hash_chain(ledger: MetadataLedger) -> None:
    """Each stage's input must be the previous stage's output, an input an earlier stage shared
    (sibling branches of a parallel block), or a recorded aggregation of directories that earlier
    stages produced (one of them the previous stage's output).
    """
    if len(ledger.entries) < 2:
        return
    produced = {ledger.entries[0].input_hash, ledger.entries[0].output_hash}
    earlier_inputs = {ledger.entries[0].input_hash}
    for index in range(1, len(ledger.entries)):
        previous = ledger.entries[index - 1]
        current = ledger.entries[index]
        if (
            current.input_hash == previous.output_hash
            or current.input_hash in earlier_inputs
            or previous.output_hash in _aggregated_from(current.input_hash, ledger.aggregations, produced)
        ):
            produced.update((current.input_hash, current.output_hash))
            earlier_inputs.add(current.input_hash)
            continue
        raise ValueError(
            f"Ledger hash-chain break at stage {index} ({current.stage_name}): "
            f"input_hash {current.input_hash!r} != previous output_hash {previous.output_hash!r} "
            "and is neither an earlier stage's input nor a recorded aggregation of earlier outputs"
        )
