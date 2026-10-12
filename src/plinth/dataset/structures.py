"""Core data structures for pipeline manifests, schemas, and metadata ledgers."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import yaml

from plinth.dataset.identity import (
    ManifestIdentity,
    apply_column_aliases,
    key_match_mask,
    normalize_entity_id,
    normalize_identity_columns,
    resolve_unique_key,
    row_key_values,
)
from plinth.dataset.manifest_paths import dataset_schema_path
from plinth.dataset.media import MediaSpec

logger = logging.getLogger(__name__)

SCHEMA_FORMAT = 1
"""Current ``dataset_schema.yaml`` format; every persisted schema states it in ``schema_format``."""


def schema_format_of(data: Dict[str, Any]) -> Optional[int]:
    """The mapping's ``schema_format`` (``None`` when absent); must be an integer when present."""
    version = data.get("schema_format")
    if version is None:
        return None
    if isinstance(version, bool) or not (isinstance(version, int) or (isinstance(version, str) and version.isdigit())):
        raise ValueError(f"invalid schema_format {version!r}: expected an integer")
    return int(version)


@dataclass
class DatasetSchema:
    """Structure and validation rules for a dataset manifest."""

    unique_key: List[str] = field(default_factory=list)
    identity: ManifestIdentity = field(default_factory=ManifestIdentity)
    columns: Dict[str, str] = field(default_factory=dict)
    media: MediaSpec = field(default_factory=MediaSpec)

    def effective_unique_key(
        self,
        left_columns: Set[str],
        right_columns: Optional[Set[str]] = None,
    ) -> List[str]:
        return resolve_unique_key(self.unique_key, self.identity, left_columns, right_columns)

    def to_dict(self) -> Dict[str, Any]:
        """Explicit, self-describing mapping: every field is written, defaults included."""
        return {
            "schema_format": SCHEMA_FORMAT,
            "unique_key": list(self.unique_key),
            "identity": asdict(self.identity),
            "columns": dict(self.columns),
            "media": asdict(self.media),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source: Optional[Path] = None) -> "DatasetSchema":
        """Build a schema from a persisted mapping, which must state a supported ``schema_format``."""
        version = schema_format_of(data)
        where = f" {source}" if source else ""
        if version is None or version < SCHEMA_FORMAT:
            raise ValueError(
                f"dataset schema{where} has no supported schema_format (expected {SCHEMA_FORMAT}); "
                "write every field explicitly and stamp schema_format"
            )
        if version > SCHEMA_FORMAT:
            raise ValueError(
                f"dataset schema{where} has schema_format {version}; "
                f"this plinth reads up to {SCHEMA_FORMAT} — upgrade plinth"
            )
        identity_data = data.get("identity")
        identity = ManifestIdentity(**identity_data) if identity_data else ManifestIdentity()

        unique_key = data.get("unique_key") or []
        if unique_key:
            unique_key = identity.normalize_unique_key(unique_key)

        return cls(
            unique_key=unique_key,
            identity=identity,
            columns=data.get("columns") or {},
            media=MediaSpec(**data["media"]) if data.get("media") else MediaSpec(),
        )

    def to_yaml(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, sort_keys=False)

    @classmethod
    def from_yaml(cls, path: Path) -> "DatasetSchema":
        """Load ``path``; a missing file yields the defaults (``DatasetSchema()``)."""
        if not path.exists():
            return cls()
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data, source=path)

    @classmethod
    def declared_in(cls, directory: Path) -> Optional["DatasetSchema"]:
        """The schema a directory declares: its ``dataset_schema.yaml``, or ``None`` if it declares none."""
        path = dataset_schema_path(Path(directory))
        return cls.from_yaml(path) if path.exists() else None

    @classmethod
    def for_directory(cls, directory: Path) -> "DatasetSchema":
        """Schema governing a stage directory: what it declares, else ``DatasetSchema()``."""
        declared = cls.declared_in(directory)
        return declared if declared is not None else cls()

    def validate_dataframe(self, df: pd.DataFrame) -> None:
        missing_cols = set(self.columns.keys()) - set(df.columns)
        if missing_cols and len(df) > 0:
            raise ValueError(f"DataFrame missing required columns: {missing_cols}")

        if len(df) > 0:
            key_cols = self.effective_unique_key(set(df.columns))
            missing_key_cols = set(key_cols) - set(df.columns)
            if missing_key_cols:
                raise ValueError(f"DataFrame missing unique key columns: {missing_key_cols}")

            duplicates = df.duplicated(subset=key_cols)
            if duplicates.any():
                dupe_examples = df[duplicates][key_cols].head().to_dict("records")
                raise ValueError(f"Duplicate entries found for unique key {key_cols}: {dupe_examples}")


@dataclass
class MetadataLedgerEntry:
    stage_name: str
    timestamp: str
    function_name: str
    input_directory: str
    output_directory: str
    input_hash: str
    output_hash: str
    params_hash: str
    params: Dict[str, Any]
    files_processed: int
    duration_seconds: float
    arming_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetadataLedgerEntry":
        return cls(**data)


@dataclass
class MetadataLedgerAggregation:
    """A block merging its input directories into one: the merged directory's hash and its inputs'.

    Lets the hash chain cross a join, whose input directory no stage wrote.
    """

    block_name: str
    input_hashes: List[str]
    output_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetadataLedgerAggregation":
        return cls(
            block_name=str(data["block_name"]),
            input_hashes=[str(h) for h in data.get("input_hashes", [])],
            output_hash=str(data["output_hash"]),
        )


@dataclass
class MetadataLedger:
    schema_version: str = "1.0"
    hierarchy_schema: Optional[Dict[str, Any]] = None
    """Deprecated, ignored by the runtime; carried through so older ledgers round-trip unchanged."""
    entries: List[MetadataLedgerEntry] = field(default_factory=list)
    aggregations: List[MetadataLedgerAggregation] = field(default_factory=list)

    def append(self, entry: MetadataLedgerEntry) -> None:
        self.entries.append(entry)

    def record_aggregation(self, aggregation: MetadataLedgerAggregation) -> None:
        if aggregation not in self.aggregations:
            self.aggregations.append(aggregation)

    def to_yaml(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": self.schema_version,
            "pipeline_version": self.get_pipeline_version(),
            "stage_history": self.get_stage_history(),
            "hierarchy_schema": self.hierarchy_schema,
            "entries": [entry.to_dict() for entry in self.entries],
            "aggregations": [aggregation.to_dict() for aggregation in self.aggregations],
        }
        with open(path, "w") as f:
            f.write("# Metadata Ledger - Cumulative Processing History\n")
            f.write("# This file tracks all pipeline stages applied to this dataset\n")
            f.write(f"# Pipeline: {' → '.join(self.get_stage_history())}\n")
            f.write(f"# Version: {self.get_pipeline_version()}\n\n")
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, path: Path) -> "MetadataLedger":
        if not path.exists():
            return cls()
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if not data:
            return cls()

        hierarchy_schema = data.get("hierarchy_schema") or None
        entries = [MetadataLedgerEntry.from_dict(entry_data) for entry_data in data.get("entries", [])]
        aggregations = [MetadataLedgerAggregation.from_dict(item) for item in data.get("aggregations") or []]
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            hierarchy_schema=hierarchy_schema,
            entries=entries,
            aggregations=aggregations,
        )

    @classmethod
    def from_directory(cls, directory: Path, filename: str = "metadata_ledger.yaml") -> "MetadataLedger":
        ledger_path = directory / filename
        return cls.from_yaml(ledger_path) if ledger_path.exists() else cls()

    def get_pipeline_version(self) -> str:
        if not self.entries:
            return "v1_raw"
        version_parts = ["v1"]
        for entry in self.entries:
            short_hash = entry.output_hash[:4] if entry.output_hash else "0000"
            version_parts.append(short_hash)
        return "_".join(version_parts)

    def get_stage_history(self) -> List[str]:
        return [entry.stage_name for entry in self.entries]

    def upstream_directories(self) -> List[Path]:
        """Input directories of the recorded stages, most recent first, without duplicates."""
        seen: Dict[str, None] = {}
        for entry in reversed(self.entries):
            if entry.input_directory:
                seen.setdefault(entry.input_directory, None)
        return [Path(directory) for directory in seen]

    def validate_consistency(self) -> bool:
        for i in range(1, len(self.entries)):
            if self.entries[i].input_hash != self.entries[i - 1].output_hash:
                return False
        return True


class DatasetManifest:
    """DataFrame-backed manifest with schema-driven identity."""

    def __init__(self, df: Optional[pd.DataFrame] = None, schema: Optional[DatasetSchema] = None) -> None:
        self._schema = schema or DatasetSchema()
        identity = self._schema.identity

        if df is None:
            empty_cols = identity.canonical_columns()
            self.df = pd.DataFrame(columns=empty_cols)
        else:
            working = apply_column_aliases(df, identity)
            self.df = normalize_identity_columns(working, identity)

    @property
    def schema(self) -> DatasetSchema:
        return self._schema

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        if idx >= len(self.df):
            raise IndexError("DatasetManifest index out of range")
        return {str(key): value for key, value in self.df.iloc[idx].to_dict().items()}

    @classmethod
    def from_csv(cls, path: Path, schema: Optional[DatasetSchema] = None) -> "DatasetManifest":
        schema = schema or DatasetSchema()
        if not path.exists():
            return cls(schema=schema)

        try:
            df = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return cls(schema=schema)
        except (pd.errors.ParserError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to load manifest from {path}: {e}") from e
        df = df.where(pd.notnull(df), None)  # type: ignore[call-overload]
        return cls(df, schema=schema)

    def to_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        identity = self._schema.identity
        lead_cols = [c for c in identity.canonical_columns() if c in self.df.columns]
        other_cols = [c for c in self.df.columns if c not in lead_cols]
        self.df[lead_cols + other_cols].to_csv(path, index=False)

    def validate_against_schema(self, schema: DatasetSchema) -> None:
        schema.validate_dataframe(self.df)

    def merge(
        self,
        other: "DatasetManifest",
        unique_key: Optional[List[str]] = None,
        schema: Optional[DatasetSchema] = None,
    ) -> "DatasetManifest":
        schema = schema or self._schema
        left_cols = set(self.df.columns)
        right_cols = set(other.df.columns)

        if unique_key is None:
            unique_key = schema.effective_unique_key(left_cols, right_cols)

        if self.df.empty:
            return DatasetManifest(other.df.copy(), schema=schema)
        if other.df.empty:
            return DatasetManifest(self.df.copy(), schema=schema)

        for key in unique_key:
            if key not in self.df.columns:
                raise ValueError(f"Unique key '{key}' missing from self manifest")
            if key not in other.df.columns:
                raise ValueError(f"Unique key '{key}' missing from other manifest")

        try:
            merged = pd.merge(
                self.df, other.df, on=unique_key, how="outer", suffixes=("_x", "_y"), indicator=True
            )
        except Exception as e:
            raise ValueError(f"Merge failed: {e}") from e

        final_cols: Dict[str, Any] = {}
        base_columns = set(self.df.columns) | set(other.df.columns) - set(unique_key)

        for k in unique_key:
            final_cols[k] = merged[k]

        for col in base_columns:
            col_x = f"{col}_x"
            col_y = f"{col}_y"

            if col_x in merged.columns and col_y in merged.columns:
                s_x = merged[col_x]
                s_y = merged[col_y]
                both_present = s_x.notna() & s_y.notna()
                conflicts = both_present & (s_x != s_y)
                if conflicts.any():
                    final_cols[col] = s_y.combine_first(s_x)
                else:
                    final_cols[col] = s_x.combine_first(s_y)
            elif col_x in merged.columns:
                final_cols[col] = merged[col_x]
            elif col_y in merged.columns:
                final_cols[col] = merged[col_y]
            elif col in merged.columns:
                final_cols[col] = merged[col]

        final_df = pd.DataFrame(final_cols).sort_values(unique_key).reset_index(drop=True)
        return DatasetManifest(final_df, schema=schema)

    def add_row(self, row_data: Dict[str, Any]) -> None:
        new_row = pd.DataFrame([row_data])
        if self.df.empty:
            self.df = new_row
        else:
            self.df = pd.concat([self.df, new_row], ignore_index=True)

    def update_entry_by_keys(
        self,
        key_values: Dict[str, Any],
        updates: Dict[str, Any],
        unique_key: Optional[List[str]] = None,
    ) -> None:
        if not updates:
            return

        schema = self._schema
        identity = schema.identity
        entity_key = identity.entity_key

        if unique_key is None:
            unique_key = schema.effective_unique_key(set(self.df.columns))

        mask = pd.Series([True] * len(self.df), index=self.df.index)
        for key in unique_key:
            if key not in key_values:
                continue
            target = key_values[key]
            if key == entity_key:
                normalized = normalize_entity_id(target)
                if normalized is None:
                    mask &= self.df[key].isna()
                else:
                    mask &= self.df[key] == normalized
            else:
                mask &= key_match_mask(self.df[key], target, identity.key_types.get(key))

        if not mask.any():
            raise ValueError(f"Entry not found for keys: {key_values}")
        if mask.sum() > 1:
            raise ValueError(f"Entry not unique for keys: {key_values}")

        for key, value in updates.items():
            if key not in self.df.columns:
                self.df[key] = None
            self.df.loc[mask, key] = value

    def update_entry_at(self, position: int, updates: Dict[str, Any]) -> None:
        """Apply ``updates`` to the row at ``position`` (0-based, as in ``manifest[position]``)."""
        if not updates:
            return
        label = self.df.index[position]
        for key, value in updates.items():
            if key not in self.df.columns:
                self.df[key] = None
            self.df.loc[label, key] = value

    def has_unique_rows(self) -> bool:
        """Whether the schema's effective unique key identifies every row (merges align on it)."""
        key = self._schema.effective_unique_key(set(self.df.columns))
        return not self.df.duplicated(subset=key).any()

    def update_entry_for_row(self, row: Dict[str, Any], updates: Dict[str, Any]) -> None:
        unique_key = self._schema.effective_unique_key(set(self.df.columns))
        key_values = row_key_values(row, unique_key)
        self.update_entry_by_keys(key_values, updates, unique_key=unique_key)
