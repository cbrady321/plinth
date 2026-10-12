"""StageIntent field behavior audit."""

from __future__ import annotations

from plinth.intent import StageIntent
from plinth.runtime.manifest_policy import should_replace_manifest


def test_allow_partial_success_field_exists_and_defaults_false() -> None:
    intent = StageIntent(reads_files=False, modifies_files=False)
    assert intent.allow_partial_success is False
    assert intent.max_dropped_rows is None


def test_filters_rows_toggles_replace_policy() -> None:
    base = StageIntent(
        write_columns={"marker": "str"},
        reads_files=False,
        modifies_files=False,
    )
    filtered = StageIntent(
        write_columns={"marker": "str"},
        filters_rows=True,
        reads_files=False,
        modifies_files=False,
    )
    assert should_replace_manifest(base) is False
    assert should_replace_manifest(filtered) is True


def test_modifies_files_declared_on_intent() -> None:
    assert StageIntent(modifies_files=True, reads_files=False).modifies_files is True
    assert StageIntent(modifies_files=False, reads_files=False).modifies_files is False


def test_removed_dead_fields_not_on_intent_surface() -> None:
    intent = StageIntent(reads_files=False, modifies_files=False)
    assert not hasattr(intent, "delete_columns")
    assert not hasattr(intent, "deletes_files")
    assert not hasattr(intent, "renames_files")
