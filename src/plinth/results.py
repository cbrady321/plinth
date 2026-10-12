"""Type-safe results for pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class ActionType(Enum):
    """Action to perform on the manifest row."""

    UPDATE = auto()  # Update existing row
    FILTER = auto()  # Remove row
    EXPAND = auto()  # Replace row with multiple new rows
    AGGREGATE = auto()  # Result of an aggregation operation


@dataclass
class StageOutcome:
    """
    Encapsulates the result of a stage processing operation.
    Replaces loose dictionaries with typed actions.

    ``updates`` and ``expanded_rows`` values should use core manifest keys from
    ``plinth.rows.CoreManifestRow`` plus any domain columns declared in
    ``StageIntent.write_columns``. This is a typing/documentation convention
    only — row shapes are not runtime-validated.
    """

    updates: Dict[str, Any] = field(default_factory=dict)
    action: ActionType = ActionType.UPDATE
    expanded_rows: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def update(cls, **kwargs) -> StageOutcome:
        return cls(updates=kwargs, action=ActionType.UPDATE)

    @classmethod
    def filter(cls) -> StageOutcome:
        return cls(action=ActionType.FILTER)

    @classmethod
    def expand(cls, rows: List[Dict[str, Any]]) -> StageOutcome:
        return cls(action=ActionType.EXPAND, expanded_rows=rows)

    @classmethod
    def aggregate(cls, **kwargs) -> StageOutcome:
        return cls(updates=kwargs, action=ActionType.AGGREGATE)
