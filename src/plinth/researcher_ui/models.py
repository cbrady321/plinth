"""API response models for the researcher UI."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RunSummary(BaseModel):
    run_id: str
    status: Literal["success", "failed", "cancelled", "in_progress", "unknown"]
    started_at: str | None = None
    duration_seconds: float | None = None
    stage_count: int = 0
    pipeline_name: str | None = None


class RunListResponse(BaseModel):
    runs: list[RunSummary]
    error: str | None = None


class StageInfo(BaseModel):
    stage_path: str
    stage_name: str
    sequence_number: int | None = None
    status: Literal["completed", "in_progress", "missing_artifacts"]
    has_manifest: bool
    has_schema: bool
    has_ledger: bool
    row_count: int | None = None


class RunDetail(BaseModel):
    run_id: str
    status: str
    started_at: str | None = None
    duration_seconds: float | None = None
    run_root: str
    stages: list[StageInfo]
    pipeline_name: str | None = None


class ManifestPage(BaseModel):
    stage_path: str
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    total_rows: int
    total_pages: int = 1
    manifest_path: str | None = None
    manifest_size_bytes: int | None = None
    identity_warning: str | None = None
    entity_filter: str | None = None
    error: str | None = None


class SchemaSummary(BaseModel):
    stage_path: str
    unique_key: list[str] = Field(default_factory=list)
    identity: dict[str, Any] = Field(default_factory=dict)
    columns: dict[str, str] = Field(default_factory=dict)
    media: dict[str, str] = Field(default_factory=dict)
    schema_path: str | None = None
    error: str | None = None


class LedgerEntryView(BaseModel):
    stage_name: str
    stage_path: str
    timestamp: str
    input_hash: str
    output_hash: str
    params_hash: str
    params: dict[str, Any] = Field(default_factory=dict)
    predecessor_hash: str | None = None
    arming_hash: str = ""
    files_processed: int = 0
    duration_seconds: float = 0.0
    status: Literal["executed", "not_executed"] = "executed"


class LedgerTimeline(BaseModel):
    run_id: str
    entries: list[LedgerEntryView]
    integrity_ok: bool
    integrity_error: str | None = None
    error: str | None = None


class RowFailure(BaseModel):
    entity_id: str | None = None
    row_index: int | None = None
    stage_path: str
    error_message: str


class FailureReport(BaseModel):
    run_id: str
    status: str
    first_failing_stage: str | None = None
    stage_error: str | None = None
    stack_summary: str | None = None
    row_failures: list[RowFailure] = Field(default_factory=list)
    cancelled_branches: list[str] = Field(default_factory=list)
    log_tail: str | None = None
    error_kind: Literal["stage_logic", "infrastructure", "unknown"] = "unknown"
    error: str | None = None


class ArtifactNode(BaseModel):
    name: str
    path: str
    kind: Literal["directory", "file"]
    size_bytes: int | None = None
    modified_at: str | None = None
    children: list[ArtifactNode] | None = None
    export_label: str | None = None
    export_warning: str | None = None
    manifest_link: bool = False


class ArtifactTree(BaseModel):
    run_id: str
    root: ArtifactNode
    error: str | None = None


class CompareConfigDiff(BaseModel):
    run_ids: list[str]
    sections: list[dict[str, Any]]
    unavailable: list[str] = Field(default_factory=list)
    structural_diffs: list[dict[str, Any]] = Field(default_factory=list)


class ManifestSummaryRow(BaseModel):
    stage_path: str
    per_run: dict[str, dict[str, Any]]
    mismatch: bool = False


class ManifestSummaryCompare(BaseModel):
    run_ids: list[str]
    rows: list[ManifestSummaryRow]


class EntityDiffPage(BaseModel):
    run_ids: list[str]
    stage_path: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    added: list[dict[str, Any]] = Field(default_factory=list)
    removed: list[dict[str, Any]] = Field(default_factory=list)
    changed: list[dict[str, Any]] = Field(default_factory=list)
    page: int = 1
    page_size: int = 50
    total_items: int = 0
    total_pages: int = 1
    identity_warning: str | None = None
    error: str | None = None


class LedgerCompareRow(BaseModel):
    stage_path: str
    per_run: dict[str, dict[str, Any]]
    hash_mismatch: bool = False


class LedgerCompare(BaseModel):
    run_ids: list[str]
    rows: list[LedgerCompareRow]


class ExportRequest(BaseModel):
    run_ids: list[str]
    sections: list[str] = Field(default_factory=lambda: ["config", "manifest_summary", "ledger"])
    format: Literal["markdown", "json"] = "markdown"
    stage_path: str | None = None
