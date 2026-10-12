"""Ledger provenance hashes cover row data, the schema and file paths, not just file bytes."""

from __future__ import annotations

import hashlib
import importlib
import shutil
from pathlib import Path

import pandas as pd
import pytest

from plinth.dataset.structures import DatasetSchema, MetadataLedger
from plinth.runtime.hashing import compute_directory_hash

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _write_manifest(directory: Path, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(directory / "manifest.csv", index=False)


def _tabular_dir(tmp_path: Path, amount: float = 10.0) -> Path:
    directory = tmp_path / "stage"
    _write_manifest(directory, [{"entity_id": "r1", "amount": amount}, {"entity_id": "r2", "amount": 3.5}])
    return directory


def test_missing_directory_hashes_to_zeroes(tmp_path: Path) -> None:
    assert compute_directory_hash(tmp_path / "absent") == "0" * 64


def test_rows_without_files_still_hash_their_data(tmp_path: Path) -> None:
    assert compute_directory_hash(_tabular_dir(tmp_path)) != EMPTY_SHA256


def test_changing_a_manifest_cell_changes_the_hash(tmp_path: Path) -> None:
    before = compute_directory_hash(_tabular_dir(tmp_path / "a", amount=10.0))
    after = compute_directory_hash(_tabular_dir(tmp_path / "b", amount=11.0))
    assert before != after


def test_row_and_column_order_do_not_matter(tmp_path: Path) -> None:
    _write_manifest(tmp_path / "a", [{"entity_id": "r1", "x": 1}, {"entity_id": "r2", "x": 2}])
    _write_manifest(tmp_path / "b", [{"x": 2, "entity_id": "r2"}, {"x": 1, "entity_id": "r1"}])
    assert compute_directory_hash(tmp_path / "a") == compute_directory_hash(tmp_path / "b")


def test_schema_is_covered(tmp_path: Path) -> None:
    directory = _tabular_dir(tmp_path)
    DatasetSchema(unique_key=["entity_id"]).to_yaml(directory / "dataset_schema.yaml")
    with_key = compute_directory_hash(directory)
    DatasetSchema(unique_key=[]).to_yaml(directory / "dataset_schema.yaml")
    assert compute_directory_hash(directory) != with_key


def test_ledger_file_is_excluded(tmp_path: Path) -> None:
    directory = _tabular_dir(tmp_path)
    before = compute_directory_hash(directory)
    MetadataLedger().to_yaml(directory / "metadata_ledger.yaml")
    assert compute_directory_hash(directory) == before


def _file_backed_dir(directory: Path, name: str = "a.bin", content: bytes = b"payload") -> Path:
    (directory / "files").mkdir(parents=True)
    (directory / "files" / name).write_bytes(content)
    _write_manifest(directory, [{"entity_id": "r1", "file_path": f"files/{name}"}])
    return directory


def test_renaming_a_file_changes_the_hash(tmp_path: Path) -> None:
    directory = _file_backed_dir(tmp_path / "stage")
    before = compute_directory_hash(directory)
    (directory / "files" / "a.bin").rename(directory / "files" / "b.bin")
    assert compute_directory_hash(directory) != before


def test_file_content_changes_the_hash(tmp_path: Path) -> None:
    first = compute_directory_hash(_file_backed_dir(tmp_path / "a", content=b"one"))
    second = compute_directory_hash(_file_backed_dir(tmp_path / "b", content=b"two"))
    assert first != second


def test_hash_is_location_independent(tmp_path: Path) -> None:
    directory = _file_backed_dir(tmp_path / "here")
    DatasetSchema().to_yaml(directory / "dataset_schema.yaml")
    moved = tmp_path / "elsewhere" / "nested"
    shutil.copytree(directory, moved)
    assert compute_directory_hash(moved) == compute_directory_hash(directory)


def test_large_files_stream_in_chunks(tmp_path: Path) -> None:
    big = bytes(range(256)) * 9000  # > one read chunk
    first = compute_directory_hash(_file_backed_dir(tmp_path / "a", content=big))
    second = compute_directory_hash(_file_backed_dir(tmp_path / "b", content=big[:-1] + b"\x00"))
    assert first != second


@pytest.mark.usefixtures("isolated_registry")
def test_tabular_pipeline_ledger_hashes_are_distinct_and_non_empty(tmp_path: Path) -> None:
    importlib.import_module("examples.tabular_records").main(tmp_path)
    run_dir = tmp_path / "data" / "pipeline" / "runs" / "tabular_records"
    ledger = max(
        (MetadataLedger.from_yaml(path) for path in run_dir.rglob("metadata_ledger.yaml")),
        key=lambda candidate: len(candidate.entries),
    )
    assert len(ledger.entries) == 3
    hashes = [entry.input_hash for entry in ledger.entries] + [ledger.entries[-1].output_hash]
    assert EMPTY_SHA256 not in hashes
    assert len(set(hashes)) == len(hashes), hashes
