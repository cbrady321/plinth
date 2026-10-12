"""Row failure policy enforcement for typical stage processing."""

from __future__ import annotations

import logging
from typing import Any

from plinth.intent import StageIntent

logger = logging.getLogger(__name__)


class RowFailurePolicy:
    def __init__(self, stage: Any, intent: StageIntent) -> None:
        self._stage = stage
        self._intent = intent

    def record_failure(self, row_index: int, cause: str) -> None:
        if self._intent.allow_partial_success:
            self._stage._dropped_rows += 1
            logger.warning(
                "Stage %s dropped row %s (%s); dropped_rows=%s",
                self._stage.stage_name,
                row_index,
                cause,
                self._stage._dropped_rows,
            )
            return
        raise ValueError(
            f"Stage {self._stage.stage_name} failed at row {row_index} (author contract §Row failure policy): {cause}"
        )

    def finalize(self) -> None:
        dropped = self._stage._dropped_rows
        if not self._intent.allow_partial_success:
            return
        limit = self._intent.max_dropped_rows
        if limit is not None and dropped > limit:
            raise ValueError(
                f"Stage {self._stage.stage_name} dropped {dropped} rows, "
                f"exceeding StageIntent.max_dropped_rows={limit} "
                f"(author contract §Row failure policy)"
            )
