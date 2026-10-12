"""Which manifest column points at each row's file, and where outputs are written."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

NO_SOURCE_FILE = Path("<no-source-file>")
"""``input_path`` handed to ``process_file`` for rows whose ``path_column`` is empty or absent
(e.g. purely tabular datasets). It never exists on disk; test with ``input_path == NO_SOURCE_FILE``."""

SOURCE_PATH_KEY = "source_path"
"""Key the runtime sets on ``process_file`` metadata to the resolved input path, unless the input
manifest has a column of that name: then the row's own value is passed through untouched. The
runtime-set value is never persisted; it is dropped from returned rows and updates."""


@dataclass(frozen=True)
class MediaSpec:
    """Declares the file-pointer convention of a dataset.

    Owned by ``DatasetSchema.media`` and persisted in ``dataset_schema.yaml``.

    - ``path_column``: manifest column holding each row's file path (relative values are
      anchored at the stage directory).
    - ``subdir``: subdirectory of a stage output directory where files are written.
    - ``name_column``: optional manifest column holding the row's file name, used to name
      output files and to normalize paths for snapshots. Empty means "basename of the path".
    """

    path_column: str = "file_path"
    subdir: str = "files"
    name_column: str = ""

    def source_path(
        self, row: Mapping[str, Any], base_dir: Path, upstream_dirs: Sequence[Path] = ()
    ) -> Optional[Path]:
        """Resolve the row's file path.

        Relative values are anchored at ``base_dir``. Stages that do not modify files pass references
        through without copying the files, so a relative value whose file is not under ``base_dir``
        resolves against ``upstream_dirs`` (nearest first), never escaping the directory it resolves in.
        When no directory holds the file, the ``base_dir`` anchoring is returned.
        """
        raw = row.get(self.path_column)
        if _is_missing(raw):
            return None
        path = Path(str(raw))
        if path.is_absolute():
            return path
        local = Path(base_dir) / path
        if local.exists():
            return local
        for directory in upstream_dirs:
            candidate = Path(directory) / path
            if candidate.exists() and candidate.resolve().is_relative_to(Path(directory).resolve()):
                return candidate
        return local

    def file_name(self, row: Mapping[str, Any], source_path: Path) -> str:
        """Name for the row's output file: ``name_column`` when declared and set, else the basename."""
        if self.name_column:
            value = row.get(self.name_column)
            if not _is_missing(value):
                return str(value)
        return source_path.name

    def portable_path(self, row: Mapping[str, Any]) -> Optional[str]:
        """Location-independent ``<subdir>/<file name>`` form of the row's path (for snapshots).

        ``None`` means "leave the cell as is": the row has no ``path_column``, or no file name can
        be derived. With ``name_column`` declared the name comes from that column only (the path
        itself may be empty); without it, from the basename of the path.
        """
        if self.path_column not in row:
            return None
        if self.name_column:
            name = row.get(self.name_column)
            return None if _is_missing(name) else self.relative_path(str(name))
        raw = row.get(self.path_column)
        return None if _is_missing(raw) else self.relative_path(Path(str(raw)).name)

    def output_path(self, output_dir: Path, filename: str) -> Path:
        return Path(output_dir) / self.subdir / filename

    def relative_path(self, filename: str) -> str:
        return f"{self.subdir}/{filename}"


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
