"""Stage execution context abstraction for pipeline stages."""

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Sequence

from plinth.dataset.manifest_paths import dataset_schema_path, manifest_csv_path
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetManifest, DatasetSchema, MetadataLedger
from plinth.file_ref import FileRef


def _ledger_entry_signature(entry) -> tuple[str, str, str]:
    return (entry.stage_name, entry.input_hash, entry.output_hash)


def _merge_ledgers_from_directories(input_dirs: List[Path]) -> MetadataLedger:
    ledgers: list[MetadataLedger] = []
    for directory in input_dirs:
        ledger = MetadataLedger.from_directory(directory)
        if ledger.entries:
            ledgers.append(ledger)
    if not ledgers:
        return MetadataLedger()
    if len(ledgers) == 1:
        return ledgers[0]
    merged = _merge_ledger_entries(ledgers)
    for ledger in ledgers:
        for aggregation in ledger.aggregations:
            merged.record_aggregation(aggregation)
    return merged


def _merge_ledger_entries(ledgers: List[MetadataLedger]) -> MetadataLedger:
    entry_lists = [ledger.entries for ledger in ledgers]
    prefix_len = 0
    min_len = min(len(entries) for entries in entry_lists)
    for index in range(min_len):
        reference = entry_lists[0][index]
        signature = _ledger_entry_signature(reference)
        if all(_ledger_entry_signature(entries[index]) == signature for entries in entry_lists):
            prefix_len = index + 1
        else:
            break

    has_branch_suffix = any(len(entries) > prefix_len for entries in entry_lists)
    if prefix_len > 0 and has_branch_suffix:
        merged = MetadataLedger()
        for entry in entry_lists[0][:prefix_len]:
            merged.append(entry)
        for entries in entry_lists:
            for entry in entries[prefix_len:]:
                merged.append(entry)
        return merged

    merged = MetadataLedger()
    for ledger in ledgers:
        for entry in ledger.entries:
            merged.append(entry)
    return merged


def _find_row(manifest: Optional[DatasetManifest], key_values: dict):
    """Return the first manifest row matching ``key_values``."""
    if manifest is None:
        raise ValueError("No manifest available to resolve paths")
    df = manifest.df
    mask = None
    for k, v in key_values.items():
        if k in df.columns:
            current = df[k].astype(str) == str(v)
            mask = current if mask is None else mask & current
    if mask is None or not mask.any():
        raise ValueError(f"Entry not found for keys: {key_values}")
    return df[mask].iloc[0]


def _row_media_path(
    row, media: MediaSpec, input_dir: Path, key_values: dict, upstream_dirs: Sequence[Path] = ()
) -> Path:
    path = media.source_path(row, input_dir, upstream_dirs)
    if path is None:
        raise ValueError(f"No {media.path_column} found for keys: {key_values}")
    return path


def _write_artifact(output_dir: Path, media: MediaSpec, file_ref: FileRef, name_hint: str) -> Path:
    """Persist ``file_ref`` under ``output_dir/<media.subdir>/`` (bytes or an existing source file)."""
    filename = name_hint if name_hint.endswith(file_ref.extension) else f"{name_hint}{file_ref.extension}"
    target_path = media.output_path(output_dir, filename)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if file_ref.source_path:
        if not file_ref.source_path.exists():
            raise FileNotFoundError(f"Source artifact not found: {file_ref.source_path}")
        shutil.copy2(file_ref.source_path, target_path)
    elif file_ref.content is not None:
        if not isinstance(file_ref.content, bytes):
            raise TypeError(f"FileRef.content must be bytes, got {type(file_ref.content).__name__}")
        target_path.write_bytes(file_ref.content)
    return target_path


class StageContext(ABC):
    """Abstract interface for stage execution context."""

    @abstractmethod
    def get_input_dir(self) -> Path:
        """Get input directory for this stage."""
        pass

    @abstractmethod
    def get_output_dir(self) -> Path:
        """Get output directory for this stage."""
        pass

    @abstractmethod
    def get_ledger(self) -> MetadataLedger:
        """Get metadata ledger (cumulative from previous stages)."""
        pass

    @abstractmethod
    def get_manifest(self) -> Optional[DatasetManifest]:
        """Get dataset manifest if available (from input directory)."""
        pass

    @abstractmethod
    def get_schema(self) -> DatasetSchema:
        """Get dataset schema (from input directory or default)."""
        pass

    @abstractmethod
    def save_schema(self, schema: DatasetSchema) -> None:
        """Save dataset schema to output directory."""
        pass

    @abstractmethod
    def update_manifest(self, updates: DatasetManifest, replace: bool = False) -> None:
        """
        Update manifest with new entries/modifications.

        Automatically:
        - Loads existing manifest from input directory
        - Merges with provided updates (unless replace=True)
        - Writes merged manifest to output directory

        Args:
            updates: New manifest entries to add/merge
            replace: If True, completely replace manifest without merging
        """
        pass

    @abstractmethod
    def get_input_path(self, **key_values) -> Path:
        """
        Resolve file path for a given entry key.

        Args:
            **key_values: Key-value pairs identifying the entry (e.g., entity_id='e1', part=1)

        Returns:
            Resolved Path object (absolute)
        """
        pass

    @abstractmethod
    def save_artifact(self, file_ref: FileRef, name_hint: str) -> Path:
        """
        Persist an artifact yielded by a stage.

        Args:
            file_ref: The file reference (content or path)
            name_hint: Suggested filename (without extension if extension provided in FileRef)

        Returns:
            Absolute path to the saved artifact
        """
        pass


class FileSystemStageContext(StageContext):
    """Concrete implementation using filesystem paths."""

    def __init__(self, input_dir: Path, output_dir: Path, manifest: Optional[DatasetManifest] = None):
        self._input_dir = input_dir
        self._output_dir = output_dir
        self._manifest = manifest
        self._ledger: Optional[MetadataLedger] = None
        self._schema: Optional[DatasetSchema] = None

    def get_input_dir(self) -> Path:
        return self._input_dir

    def get_output_dir(self) -> Path:
        return self._output_dir

    def get_ledger(self) -> MetadataLedger:
        if self._ledger is None:
            self._ledger = MetadataLedger.from_directory(self._input_dir)
        return self._ledger

    def get_manifest(self) -> Optional[DatasetManifest]:
        if self._manifest is None:
            manifest_path = manifest_csv_path(self._input_dir)
            if manifest_path.exists():
                schema = self.get_schema()
                self._manifest = DatasetManifest.from_csv(manifest_path, schema=schema)
        return self._manifest

    def get_schema(self) -> DatasetSchema:
        if self._schema is None:
            self._schema = DatasetSchema.for_directory(self._input_dir)
        return self._schema

    def save_schema(self, schema: DatasetSchema) -> None:
        schema.to_yaml(dataset_schema_path(self._output_dir))
        self._schema = schema

    def get_input_path(self, **key_values) -> Path:
        row = _find_row(self.get_manifest(), key_values)
        media = self.get_schema().media
        upstream_dirs = self.get_ledger().upstream_directories()
        path = _row_media_path(row, media, self._input_dir, key_values, upstream_dirs)
        roots = [self._input_dir.resolve(), *(d.resolve() for d in upstream_dirs)]
        if not any(path.resolve().is_relative_to(root) for root in roots):
            raise ValueError(
                f"{media.path_column} resolves outside input directory "
                f"({path.resolve()} not under {self._input_dir.resolve()}; author contract §Propagation)"
            )
        return path

    def update_manifest(self, updates: DatasetManifest, replace: bool = False) -> None:
        """Merge updates with existing manifest and save to output."""
        if replace:
            # Replace entire manifest without merging
            merged = updates
        else:
            existing = self.get_manifest()

            if existing:
                # Merge existing with updates
                merged = self._merge_manifests(existing, updates)
            else:
                merged = updates

        # Update cache so subsequent calls see the updates
        self._manifest = merged

        output_path = manifest_csv_path(self._output_dir)
        merged.to_csv(output_path)

    def _merge_manifests(self, existing: DatasetManifest, updates: DatasetManifest) -> DatasetManifest:
        schema = self.get_schema()
        unique_key = schema.effective_unique_key(set(existing.df.columns), set(updates.df.columns))
        return existing.merge(updates, unique_key=unique_key, schema=schema)

    def save_artifact(self, file_ref: FileRef, name_hint: str) -> Path:
        """Persist an artifact yielded by a stage."""
        return _write_artifact(self._output_dir, self.get_schema().media, file_ref, name_hint)


class MultiInputStageContext(StageContext):
    """Context for stages that receive multiple input directories (merge scenarios)."""

    def __init__(self, input_dirs: List[Path], output_dir: Path, manifest: Optional[DatasetManifest] = None):
        # Use the first input as primary for APIs requiring a single dir
        self._input_dirs = input_dirs
        self._primary_input_dir = input_dirs[0] if input_dirs else output_dir
        self._output_dir = output_dir
        self._manifest = manifest
        self._merged_ledger: Optional[MetadataLedger] = None
        self._schema: Optional[DatasetSchema] = None

    def get_input_dir(self) -> Path:
        return self._primary_input_dir

    def get_input_dirs(self) -> List[Path]:
        return self._input_dirs

    def get_output_dir(self) -> Path:
        return self._output_dir

    def get_ledger(self) -> MetadataLedger:
        if self._merged_ledger is None:
            self._merged_ledger = _merge_ledgers_from_directories(self._input_dirs)
        return self._merged_ledger

    def get_manifest(self) -> Optional[DatasetManifest]:
        if self._manifest is not None:
            return self._manifest
        # Merge manifests from all inputs if present
        merged: Optional[DatasetManifest] = None
        for d in self._input_dirs:
            manifest_path = manifest_csv_path(d)
            if manifest_path.exists():
                schema = self.get_schema()
                m = DatasetManifest.from_csv(manifest_path, schema=schema)

                # Normalize paths to absolute to prevent ambiguity after merge
                column = schema.media.path_column
                if column in m.df.columns:

                    upstream_dirs = MetadataLedger.from_directory(d).upstream_directories()

                    def normalize_path(p, d=d, upstream_dirs=upstream_dirs):
                        if not p:
                            return p
                        resolved = schema.media.source_path({column: p}, d, upstream_dirs)
                        return p if resolved is None else str(resolved)

                    m.df[column] = m.df[column].apply(normalize_path)

                merged = m if merged is None else merged.merge(m, schema=schema)
        self._manifest = merged
        return self._manifest

    def get_schema(self) -> DatasetSchema:
        """Merge schemas from all inputs."""
        if self._schema is None:
            merged_schema = DatasetSchema()

            for d in self._input_dirs:
                declared = DatasetSchema.declared_in(d)
                if declared is not None:
                    current = declared

                    # Merge logic
                    # 1. Unique keys must match
                    if set(current.unique_key) != set(merged_schema.unique_key):
                        # Only strict if merged_schema is not default (empty columns)
                        if merged_schema.columns:
                            raise ValueError(
                                f"Schema mismatch in unique_key: {current.unique_key} vs {merged_schema.unique_key}"
                            )
                        else:
                            merged_schema.unique_key = current.unique_key

                    # 2. Media spec and identity must agree across inputs
                    if merged_schema.columns and current.media != merged_schema.media:
                        raise ValueError(f"Schema mismatch in media: {current.media} vs {merged_schema.media}")
                    merged_schema.media = current.media
                    if merged_schema.columns and current.identity != merged_schema.identity:
                        raise ValueError(
                            f"Schema mismatch in identity: {current.identity} vs {merged_schema.identity}"
                        )
                    merged_schema.identity = current.identity

                    # 3. Merge columns
                    for col, dtype in current.columns.items():
                        if col in merged_schema.columns:
                            if merged_schema.columns[col] != dtype:
                                raise ValueError(
                                    f"Schema mismatch for column '{col}': {dtype} vs {merged_schema.columns[col]}"
                                )
                        else:
                            merged_schema.columns[col] = dtype

            self._schema = merged_schema
        return self._schema

    def save_schema(self, schema: DatasetSchema) -> None:
        schema.to_yaml(dataset_schema_path(self._output_dir))
        self._schema = schema

    def update_manifest(self, updates: DatasetManifest, replace: bool = False) -> None:
        if replace:
            # Replace entire manifest without merging
            merged = updates
        else:
            existing = self.get_manifest()

            if existing is None:
                merged = updates
            else:
                schema = self.get_schema()
                unique_key = schema.effective_unique_key(
                    set(existing.df.columns), set(updates.df.columns)
                )
                merged = existing.merge(updates, unique_key=unique_key, schema=schema)

        self._manifest = merged

        merged.to_csv(manifest_csv_path(self._output_dir))

    def get_input_path(self, **key_values) -> Path:
        # get_manifest normalizes paths to absolute, so no single-dir fallback applies here.
        row = _find_row(self.get_manifest(), key_values)
        path = _row_media_path(row, self.get_schema().media, self._primary_input_dir, key_values)
        if not path.is_absolute():
            raise ValueError(f"Resolved path is relative in multi-input context: {path}")
        return path

    def save_artifact(self, file_ref: FileRef, name_hint: str) -> Path:
        """Persist an artifact yielded by a stage."""
        return _write_artifact(self._output_dir, self.get_schema().media, file_ref, name_hint)


class InMemoryStageContext(StageContext):
    """In-memory stage context for zero-filesystem stage tests."""

    def __init__(
        self,
        manifest: DatasetManifest,
        schema: Optional[DatasetSchema] = None,
        ledger: Optional[MetadataLedger] = None,
        input_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        import tempfile

        self._manifest = manifest
        self._schema = schema or DatasetSchema()
        self._ledger = ledger or MetadataLedger()
        self._input_dir = input_dir or Path(tempfile.mkdtemp(prefix="inmem_in_"))
        self._output_dir = output_dir or Path(tempfile.mkdtemp(prefix="inmem_out_"))
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def get_input_dir(self) -> Path:
        return self._input_dir

    def get_output_dir(self) -> Path:
        return self._output_dir

    def get_ledger(self) -> MetadataLedger:
        return self._ledger

    def get_manifest(self) -> Optional[DatasetManifest]:
        return self._manifest

    def get_schema(self) -> DatasetSchema:
        return self._schema

    def save_schema(self, schema: DatasetSchema) -> None:
        self._schema = schema

    def update_manifest(self, updates: DatasetManifest, replace: bool = False) -> None:
        if replace or self._manifest is None:
            self._manifest = updates
            return
        unique_key = self._schema.effective_unique_key(
            set(self._manifest.df.columns), set(updates.df.columns)
        )
        self._manifest = self._manifest.merge(updates, unique_key=unique_key, schema=self._schema)

    def get_input_path(self, **key_values) -> Path:
        row = _find_row(self.get_manifest(), key_values)
        return _row_media_path(row, self._schema.media, self._input_dir, key_values)

    def save_artifact(self, file_ref: FileRef, name_hint: str) -> Path:
        if not (file_ref.source_path and file_ref.source_path.exists()) and not isinstance(file_ref.content, bytes):
            raise NotImplementedError("InMemoryStageContext supports bytes artifacts only")
        return _write_artifact(self._output_dir, self._schema.media, file_ref, name_hint)
