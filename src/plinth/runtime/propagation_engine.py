"""Input file propagation when stages do not write outputs."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from plinth.dataset.structures import DatasetManifest

logger = logging.getLogger(__name__)


class PropagationEngine:
    def propagate_if_needed(
        self,
        *,
        always_propagate: bool,
        output_path: Path,
        source_path: Path,
        path_column: str,
        filename: str,
        row: dict[str, Any],
        is_structural_change: bool,
        new_rows: Optional[list[dict[str, Any]]],
        manifest: Optional[DatasetManifest],
        row_index: Optional[int] = None,
    ) -> None:
        if not always_propagate:
            return
        if output_path.exists() or not source_path.exists() or not source_path.is_file():
            return

        logger.debug(f"  [Debug] Propagating input file for {filename}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, output_path)

        if is_structural_change and new_rows:
            new_rows[-1][path_column] = str(output_path)
        elif manifest and row_index is not None:
            manifest.update_entry_at(row_index, {path_column: str(output_path)})
        elif manifest:
            try:
                manifest.update_entry_for_row(row, {path_column: str(output_path)})
            except Exception as e:
                logger.warning(f"Failed to update manifest during propagation: {e}")
