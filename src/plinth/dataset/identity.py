"""Schema-driven manifest identity — domain-neutral entity keys for any dataset."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import pandas as pd


def normalize_entity_id(value: Any) -> Optional[str]:
    """
    Normalize an entity identifier value to a clean string or None.

    Treats None, empty strings, whitespace-only strings, float NaN, and pandas NA
    as missing (returns None). Otherwise returns a cleaned string.

    This prevents missing IDs becoming literal strings like "nan" that collapse
    distinct rows during merge and group operations.
    """
    # Handle pandas NA
    if pd.isna(value):
        return None

    # Handle None
    if value is None:
        return None

    # Handle float NaN
    if isinstance(value, float) and math.isnan(value):
        return None

    # Convert to string and strip whitespace
    try:
        s = str(value).strip()
    except Exception:
        return None

    # Empty string after stripping is missing
    if not s:
        return None

    # Special case: reject literal "nan", "None", "unknown" as they're likely
    # artifacts of stringification bugs. However, we preserve them if they're
    # explicitly provided, as they might be legitimate IDs in some datasets.
    # For now, we'll preserve them but this can be made configurable.

    return s


KEY_TYPES = ("int", "optional_int")
"""Normalization kinds for identity columns (``ManifestIdentity.key_types``).

- ``int``: coerced to integers on ingest; missing values take ``key_defaults[column]`` (required);
  matched as integers.
- ``optional_int``: stored as given with missing values as ``None``; matched as integers, where a
  ``None`` target matches missing or empty cells.

Columns without a declared kind are stored as given and matched as strings.
"""


@dataclass
class ManifestIdentity:
    """Declares how manifest rows identify entities.

    The default is a flat identity: one ``entity_id`` per row, no hierarchy, no disambiguator.
    Datasets whose rows are sub-units of an entity (pages of a document, frames of a video,
    tiles of an image, ...) declare the tiers in ``hierarchy_keys`` and, when the tier columns
    are numeric, their normalization in ``key_types`` / ``key_defaults``.
    """

    entity_key: str = "entity_id"
    hierarchy_keys: List[str] = field(default_factory=list)
    disambiguator: str = ""
    column_aliases: Dict[str, str] = field(default_factory=dict)
    key_types: Dict[str, str] = field(default_factory=dict)
    key_defaults: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = sorted(col for col, kind in self.key_types.items() if kind not in KEY_TYPES)
        if unknown:
            raise ValueError(f"ManifestIdentity.key_types has unknown kinds for {unknown}; allowed: {KEY_TYPES}")
        undefaulted = sorted(c for c, kind in self.key_types.items() if kind == "int" and c not in self.key_defaults)
        if undefaulted:
            raise ValueError(f"ManifestIdentity.key_types 'int' columns {undefaulted} need a key_defaults value")

    def canonical_columns(self) -> List[str]:
        cols = [self.entity_key]
        cols.extend(self.hierarchy_keys)
        if self.disambiguator:
            cols.append(self.disambiguator)
        return cols

    def normalize_unique_key(self, unique_key: List[str]) -> List[str]:
        """Rewrite alias names in a unique_key list to canonical names."""
        alias = self.column_aliases
        return [alias.get(k, k) for k in unique_key]


def apply_column_aliases(df: pd.DataFrame, identity: ManifestIdentity) -> pd.DataFrame:
    """Rename alias columns to canonical names on ingest."""
    out: pd.DataFrame = df.copy()
    for alias, canonical in identity.column_aliases.items():
        if alias not in out.columns:
            continue
        if canonical not in out.columns:
            out = out.rename(columns={alias: canonical})
        else:
            out = out.drop(columns=[alias])
    return out


def normalize_identity_columns(df: pd.DataFrame, identity: ManifestIdentity) -> pd.DataFrame:
    """Ensure identity columns exist, normalize entity values and apply declared ``key_types``."""
    out: pd.DataFrame = df.copy()
    if identity.entity_key not in out.columns:
        out[identity.entity_key] = None
    for key in identity.hierarchy_keys:
        if key not in out.columns:
            out[key] = identity.key_defaults.get(key)

    out[identity.entity_key] = out[identity.entity_key].apply(normalize_entity_id)
    out[identity.entity_key] = out[identity.entity_key].astype("string")

    for column, kind in identity.key_types.items():
        if column not in out.columns:
            continue
        if kind == "int":
            filled = pd.to_numeric(out[column], errors="coerce").fillna(identity.key_defaults[column])
            out[column] = filled.astype(int)
        else:
            out[column] = out[column].astype(object).where(out[column].notnull(), None)  # type: ignore[call-overload]

    return out


def key_match_mask(series: pd.Series, target: Any, kind: Optional[str]) -> pd.Series:
    """Rows of ``series`` equal to ``target`` under the declared key kind (see ``KEY_TYPES``)."""
    if kind == "optional_int":
        if target is None:
            return series.isna() | (series == "")
        return pd.to_numeric(series, errors="coerce").fillna(-1).astype(int) == int(target)
    if kind == "int":
        return series.astype(int) == int(target)
    if normalize_entity_id(target) is None:
        return series.isna() | (series.astype(object) == "")
    return series.astype(str) == str(target)


def resolve_unique_key(
    schema_unique_key: List[str],
    identity: ManifestIdentity,
    left_columns: Set[str],
    right_columns: Optional[Set[str]] = None,
) -> List[str]:
    """Resolve merge key columns present in both manifests."""
    if schema_unique_key:
        candidates = identity.normalize_unique_key(schema_unique_key)
    else:
        candidates = identity.canonical_columns()

    right = right_columns or left_columns
    resolved = [k for k in candidates if k in left_columns and k in right]
    if resolved:
        return resolved

    # Minimal fallback: entity + hierarchy keys that exist on both sides
    minimal = [identity.entity_key]
    for k in identity.hierarchy_keys:
        if k in left_columns and k in right:
            minimal.append(k)
    return minimal


def row_key_values(row: dict[str, Any], unique_key: List[str]) -> dict[str, Any]:
    """Extract key fields from a row dict for merge/update operations."""
    return {k: row.get(k) for k in unique_key if k in row}
