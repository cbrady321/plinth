"""Manifest row typing aids for stage authors.

Manifest rows are open dictionaries at runtime and are not validated against these types.
``CoreManifestRow`` names only the keys plinth itself defines; every other column
belongs to your dataset. Extend it in your project::

    class DocumentRow(CoreManifestRow, total=False):
        page: int
        text_path: str  # your DatasetSchema.media.path_column

then keep the ``process_file(..., metadata: CoreManifestRow)`` signature (narrowing a parameter
type breaks the override) and view the row as your type: ``row = cast(DocumentRow, metadata)``.
"""

from __future__ import annotations

from typing import Any, TypedDict

ManifestRow = dict[str, Any]


class CoreManifestRow(TypedDict, total=False):
    """Plinth-defined row keys (all optional: rows are open and may be partial)."""

    entity_id: str
    """Entity identifier under the default ``ManifestIdentity.entity_key``."""

    source_path: str
    """Set by the runtime on ``process_file`` metadata: the resolved input file path, or
    ``str(plinth.dataset.media.NO_SOURCE_FILE)`` for rows without one. Never persisted. When the input
    manifest has its own ``source_path`` column, that value is passed through instead; the resolved
    path is always the ``input_path`` argument."""
