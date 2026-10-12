"""Hash-chain validation tests."""

from __future__ import annotations

import pytest

from plinth.dataset.structures import MetadataLedger, MetadataLedgerAggregation, MetadataLedgerEntry
from plinth.runtime.hash_chain_validator import validate_hash_chain


def _entry(stage: str, input_hash: str, output_hash: str) -> MetadataLedgerEntry:
    return MetadataLedgerEntry(
        stage_name=stage,
        timestamp="2026-01-01T00:00:00",
        function_name="TestStage",
        input_directory="/in",
        output_directory="/out",
        input_hash=input_hash,
        output_hash=output_hash,
        params_hash="p",
        params={},
        files_processed=1,
        duration_seconds=1.0,
    )


def test_single_stage_skips_validation() -> None:
    validate_hash_chain(MetadataLedger(entries=[_entry("only", "a", "b")]))


def test_contiguous_chain_passes() -> None:
    validate_hash_chain(
        MetadataLedger(
            entries=[
                _entry("s1", "0" * 64, "aaa"),
                _entry("s2", "aaa", "bbb"),
                _entry("s3", "bbb", "ccc"),
            ]
        )
    )


def test_parallel_sibling_input_hash_allowed() -> None:
    validate_hash_chain(
        MetadataLedger(
            entries=[
                _entry("branch_a", "0" * 64, "aaa"),
                _entry("branch_b", "0" * 64, "bbb"),
                _entry("join", "bbb", "ccc"),
            ]
        )
    )


def test_broken_chain_raises_with_stage_index() -> None:
    ledger = MetadataLedger(
        entries=[
            _entry("s1", "0" * 64, "aaa"),
            _entry("s2", "broken", "bbb"),
        ]
    )
    with pytest.raises(ValueError, match="hash-chain break at stage 1"):
        validate_hash_chain(ledger)


def _aggregation(output_hash: str, *input_hashes: str) -> MetadataLedgerAggregation:
    return MetadataLedgerAggregation(block_name="split", input_hashes=list(input_hashes), output_hash=output_hash)


def test_multi_stage_branch_sibling_shares_fan_out_input() -> None:
    validate_hash_chain(
        MetadataLedger(
            entries=[
                _entry("a1", "in", "a1_out"),
                _entry("a2", "a1_out", "a2_out"),
                _entry("b1", "in", "b1_out"),
                _entry("join", "merged", "join_out"),
            ],
            aggregations=[_aggregation("merged", "a2_out", "b1_out")],
        )
    )


def test_nested_aggregation_resolves_transitively() -> None:
    validate_hash_chain(
        MetadataLedger(
            entries=[
                _entry("a", "in", "a_out"),
                _entry("b", "in", "b_out"),
                _entry("join", "outer", "join_out"),
            ],
            aggregations=[_aggregation("inner", "b_out"), _aggregation("outer", "a_out", "inner")],
        )
    )


def test_join_without_recorded_aggregation_raises() -> None:
    ledger = MetadataLedger(
        entries=[
            _entry("a", "in", "a_out"),
            _entry("b", "in", "b_out"),
            _entry("join", "merged", "join_out"),
        ]
    )
    with pytest.raises(ValueError, match="hash-chain break at stage 2"):
        validate_hash_chain(ledger)


def test_aggregation_of_unproduced_directory_raises() -> None:
    ledger = MetadataLedger(
        entries=[
            _entry("a", "in", "a_out"),
            _entry("b", "in", "b_out"),
            _entry("join", "merged", "join_out"),
        ],
        aggregations=[_aggregation("merged", "b_out", "forged")],
    )
    with pytest.raises(ValueError, match="hash-chain break at stage 2"):
        validate_hash_chain(ledger)


def test_aggregations_round_trip_through_yaml(tmp_path) -> None:
    ledger = MetadataLedger(entries=[_entry("a", "in", "a_out")], aggregations=[_aggregation("m", "a_out")])
    ledger.to_yaml(tmp_path / "metadata_ledger.yaml")
    assert MetadataLedger.from_yaml(tmp_path / "metadata_ledger.yaml").aggregations == ledger.aggregations
