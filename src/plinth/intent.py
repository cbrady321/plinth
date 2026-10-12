"""Defines the intent of a pipeline stage for validation and optimization."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class StageIntent:
    """
    Declares the intent of a stage: what it reads, writes, and modifies.

    This allows the pipeline framework to:
    1. Validate inputs before execution (check for required columns)
    2. Validate outputs after execution (check for promised columns)
    3. Detect conflicts in parallel branches (e.g., writing same column)
    4. Optimize data propagation (know if files are modified)
    5. Automatically determine manifest handling (replace vs merge)

    After creating a StageIntent, call validate() to check for common mistakes.
    """

    def __post_init__(self):
        """Validate intent configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """
        Validate intent configuration and warn about potential issues.
        """
        import warnings

        has_structural_change = (
            self.filters_rows or self.expands_rows or self.aggregates_rows or self.group_by is not None
        )

        if self.replaces_manifest and has_structural_change:
            warnings.warn(
                f"StageIntent: replaces_manifest=True is redundant when structural change flags "
                f"(filters_rows={self.filters_rows}, expands_rows={self.expands_rows}, "
                f"aggregates_rows={self.aggregates_rows}, group_by={self.group_by}) are set. "
                f"The framework will automatically replace the manifest for structural changes. "
                f"Consider removing replaces_manifest=True unless you have a specific reason.",
                UserWarning,
                stacklevel=3,
            )

    def validate_strict(self) -> None:
        """Strict validation — warnings become errors."""
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.validate()

        for warning in caught:
            raise ValueError(str(warning.message))

    # Columns required in the input manifest
    required_input_columns: Set[str] = field(default_factory=set)

    # Columns added or modified by this stage (name -> data type description)
    # Using string for type description to avoid serialization issues
    write_columns: Dict[str, str] = field(default_factory=dict)

    # Columns to append to the schema's unique_key
    # These define additional dimensions of uniqueness beyond the base key
    append_to_unique_key: Set[str] = field(default_factory=set)

    # Whether this stage creates/modifies files (requiring disk I/O)
    # If False, input files are propagated by reference (no copy)
    modifies_files: bool = False

    # Whether this stage reads the actual files (vs just metadata)
    reads_files: bool = True

    # Whether this stage replaces the entire manifest (vs merging with existing)
    #
    # IMPORTANT: This flag is rarely needed. The framework automatically determines
    # when to replace vs merge based on structural changes (filters_rows, expands_rows, etc.)
    # and in-place updates.
    #
    # Only set this to True if:
    # - Your stage creates a completely new manifest structure that cannot be merged
    # - Your stage bootstraps a manifest from directory listing (not from input manifest)
    #
    # For most stages:
    # - Use filters_rows=True if you filter rows (framework will replace automatically)
    # - Use expands_rows=True if you create multiple rows per input (framework will replace automatically)
    # - Use aggregates_rows=True if you combine multiple inputs (framework will replace automatically)
    # - For in-place updates (default), framework automatically replaces to avoid duplicates
    #
    # If you're unsure, leave this as False and let the framework decide.
    replaces_manifest: bool = False

    # --- Extended Intent for Automatic Processing ---

    # Row-level operations
    # These flags help the framework automatically determine manifest handling:
    filters_rows: bool = False  # Stage may remove some rows (quality filtering)
    expands_rows: bool = False  # Stage creates multiple output rows per input
    aggregates_rows: bool = False  # Stage combines multiple input rows into one output

    # Column operation types
    modify_columns: Set[str] = field(default_factory=set)  # Columns being modified (vs added)

    # Aggregation / Grouping
    # If set (e.g. ['entity_id']), BaseStage groups rows by these columns
    # and calls process_group() instead of process_file()
    group_by: Optional[List[str]] = None

    allow_partial_success: bool = False
    max_dropped_rows: Optional[int] = None
