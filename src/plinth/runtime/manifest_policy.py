"""Manifest replace vs merge policy."""

from __future__ import annotations

from plinth.intent import StageIntent


def should_replace_manifest(intent: StageIntent) -> bool:
    if intent.replaces_manifest:
        return True

    has_structural_change = (
        intent.filters_rows or intent.expands_rows or intent.aggregates_rows or intent.group_by is not None
    )
    if has_structural_change:
        return True

    if not intent.write_columns:
        return True

    return False
