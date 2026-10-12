"""Partial-dataset row-count guard at stage boundary."""

from __future__ import annotations

from plinth.intent import StageIntent


def assert_no_silent_row_loss(
    stage_name: str,
    intent: StageIntent,
    input_row_count: int,
    output_row_count: int,
) -> None:
    if intent.allow_partial_success:
        return
    if intent.filters_rows or intent.expands_rows or intent.aggregates_rows or intent.group_by:
        return
    if intent.replaces_manifest:
        return
    if output_row_count >= input_row_count:
        return
    raise ValueError(
        f"Stage {stage_name} completed with {output_row_count} output rows from "
        f"{input_row_count} input rows without allow_partial_success=true "
        f"(runtime/row_count_guard; author contract §Row failure policy)"
    )
