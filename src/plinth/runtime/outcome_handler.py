"""StageOutcome handling for typical stage execution."""

from __future__ import annotations

import logging
from typing import Any, Optional

from plinth.dataset.structures import DatasetManifest
from plinth.results import ActionType, StageOutcome

logger = logging.getLogger(__name__)


class OutcomeHandler:
    def __init__(self, stage_name: str, runtime_keys: frozenset[str] = frozenset()) -> None:
        """``runtime_keys``: metadata keys the runtime injected for the stage; never persisted."""
        self._stage_name = stage_name
        self._runtime_keys = runtime_keys

    def _persistable(self, row: dict[str, Any]) -> dict[str, Any]:
        if not self._runtime_keys.intersection(row):
            return row
        return {k: v for k, v in row.items() if k not in self._runtime_keys}

    def handle_result(
        self,
        result: Any,
        original_row: Optional[dict[str, Any]],
        new_rows: Optional[list[dict[str, Any]]],
        is_structural_change: bool,
        manifest: Optional[DatasetManifest] = None,
        row_index: Optional[int] = None,
    ) -> None:
        if not result:
            if is_structural_change and original_row is not None and new_rows is not None:
                new_rows.append(original_row)
            return

        if not isinstance(result, StageOutcome):
            raise TypeError(f"Stage {self._stage_name} returned {type(result).__name__}; expected StageOutcome")

        if result.action == ActionType.FILTER:
            return

        if result.action == ActionType.EXPAND:
            if new_rows is not None and result.expanded_rows:
                new_rows.extend(self._persistable(row) for row in result.expanded_rows)
            elif not is_structural_change:
                logger.warning("Stage attempted expansion but is_structural_change is False")
            return

        if result.action in (ActionType.UPDATE, ActionType.AGGREGATE):
            self._apply_updates(
                result.updates,
                original_row,
                new_rows,
                is_structural_change,
                manifest,
                row_index,
            )

    def _apply_updates(
        self,
        updates: dict[str, Any],
        original_row: Optional[dict[str, Any]],
        new_rows: Optional[list[dict[str, Any]]],
        is_structural_change: bool,
        manifest: Optional[DatasetManifest],
        row_index: Optional[int] = None,
    ) -> None:
        updates = self._persistable(updates)
        if is_structural_change:
            if new_rows is None:
                raise RuntimeError("Structural updates require new_rows collector")
            if original_row:
                updated = dict(original_row)
                updated.update(updates)
                new_rows.append(updated)
            else:
                new_rows.append(updates)
            return

        if not manifest:
            return

        clean_updates = {k: v for k, v in updates.items() if not k.startswith("_")}
        if clean_updates and row_index is not None:
            manifest.update_entry_at(row_index, clean_updates)
        elif clean_updates and original_row and manifest:
            try:
                manifest.update_entry_for_row(original_row, clean_updates)
            except Exception as e:
                logger.warning(f"Update entry failed in {self._stage_name}: {e}")
