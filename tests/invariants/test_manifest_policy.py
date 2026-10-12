"""Manifest replace vs merge policy tests."""

from __future__ import annotations

from plinth.intent import StageIntent
from plinth.runtime.manifest_policy import should_replace_manifest


def test_column_update_stage_merges_manifest() -> None:
    intent = StageIntent(
        write_columns={"category": "str"},
        reads_files=False,
        modifies_files=False,
    )
    assert should_replace_manifest(intent) is False


def test_no_write_columns_stage_replaces_manifest() -> None:
    intent = StageIntent(
        write_columns={},
        reads_files=False,
        modifies_files=False,
    )
    assert should_replace_manifest(intent) is True


def test_filter_stage_replaces_manifest() -> None:
    intent = StageIntent(
        filters_rows=True,
        reads_files=False,
        modifies_files=False,
    )
    assert should_replace_manifest(intent) is True


def test_expand_stage_replaces_manifest() -> None:
    intent = StageIntent(
        expands_rows=True,
        reads_files=False,
        modifies_files=False,
    )
    assert should_replace_manifest(intent) is True


def test_explicit_replaces_manifest_flag() -> None:
    intent = StageIntent(
        replaces_manifest=True,
        reads_files=False,
        modifies_files=False,
    )
    assert should_replace_manifest(intent) is True
