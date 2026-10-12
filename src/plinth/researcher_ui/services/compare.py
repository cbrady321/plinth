"""Cross-run comparison services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from plinth.dataset.structures import DatasetSchema
from plinth.researcher_ui.models import (
    CompareConfigDiff,
    EntityDiffPage,
    ExportRequest,
    LedgerCompare,
    LedgerCompareRow,
    ManifestSummaryCompare,
    ManifestSummaryRow,
)
from plinth.researcher_ui.services.config_diff import diff_configs
from plinth.researcher_ui.services.ledger import load_ledger_timeline
from plinth.researcher_ui.services.run_index import (
    CONFIG_SNAPSHOT,
    _schema_path,
    get_run,
    list_stages,
    resolve_run_dir,
    resolve_stage_dir,
)


def _row_dict(row: pd.Series) -> dict[str, Any]:
    return {str(key): value for key, value in row.to_dict().items()}


def _load_config_snapshot(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / CONFIG_SNAPSHOT
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None


def _flatten_dag(node: dict[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    name = node.get("name", "")
    node_type = node.get("type", "")
    current = f"{prefix}/{name}" if prefix else name
    if node_type == "stage":
        paths.append(current)
    for child in node.get("children", []) or []:
        paths.extend(_flatten_dag(child, current if node_type != "stage" else prefix))
    return paths


def compare_configs(runs_dir: Path, run_ids: list[str]) -> CompareConfigDiff:
    sections: list[dict[str, Any]] = []
    unavailable: list[str] = []
    configs: list[dict[str, Any]] = []
    available_ids: list[str] = []
    for run_id in run_ids:
        run_dir = resolve_run_dir(runs_dir, run_id)
        config = _load_config_snapshot(run_dir) if run_dir is not None else None
        if config is None:
            unavailable.append(run_id)
            continue
        sections.append({"run_id": run_id, "config": config})
        configs.append(config)
        available_ids.append(run_id)
    structural = diff_configs(configs, available_ids) if len(configs) >= 2 else []
    return CompareConfigDiff(
        run_ids=run_ids,
        sections=sections,
        unavailable=unavailable,
        structural_diffs=structural,
    )


def _manifest_summary_for_stage(run_dir: Path, stage_path: str) -> dict[str, Any] | None:
    stage_dir = run_dir / stage_path
    manifest = stage_dir / "manifest.csv"
    if not manifest.exists():
        return None
    try:
        df = pd.read_csv(manifest)
    except Exception:
        return {"unavailable": True}
    schema_path = _schema_path(stage_dir)
    columns = sorted(df.columns.tolist())
    if schema_path:
        try:
            schema = DatasetSchema.from_yaml(schema_path)
            columns = sorted(set(columns) | set(schema.columns.keys()))
        except Exception:
            pass
    return {"row_count": len(df), "columns": columns}


def compare_manifest_summaries(runs_dir: Path, run_ids: list[str]) -> ManifestSummaryCompare:
    stage_paths: set[str] = set()
    per_run_stage: dict[str, dict[str, dict[str, Any] | None]] = {run_id: {} for run_id in run_ids}

    for run_id in run_ids:
        run_dir = resolve_run_dir(runs_dir, run_id)
        if run_dir is None:
            continue
        for stage in list_stages(run_dir):
            stage_paths.add(stage.directory_path.name)
            per_run_stage[run_id][stage.directory_path.name] = _manifest_summary_for_stage(
                run_dir, stage.directory_path.name
            )

    rows: list[ManifestSummaryRow] = []
    for stage_path in sorted(stage_paths):
        per_run: dict[str, dict[str, Any]] = {}
        for run_id in run_ids:
            summary = per_run_stage.get(run_id, {}).get(stage_path)
            if summary is None:
                per_run[run_id] = {"unavailable": True}
            else:
                per_run[run_id] = summary

        summaries = [per_run[rid] for rid in run_ids if not per_run[rid].get("unavailable")]
        mismatch = False
        if len(summaries) >= 2:
            base_rows = summaries[0].get("row_count")
            base_cols = tuple(summaries[0].get("columns", []))
            mismatch = any(
                s.get("row_count") != base_rows or tuple(s.get("columns", [])) != base_cols for s in summaries[1:]
            )
        rows.append(ManifestSummaryRow(stage_path=stage_path, per_run=per_run, mismatch=mismatch))
    return ManifestSummaryCompare(run_ids=run_ids, rows=rows)


def _entity_key_columns(stage_dir: Path) -> list[str]:
    schema_path = _schema_path(stage_dir)
    if schema_path:
        try:
            schema = DatasetSchema.from_yaml(schema_path)
            manifest = stage_dir / "manifest.csv"
            cols = set(pd.read_csv(manifest, nrows=0).columns) if manifest.exists() else set()
            return schema.effective_unique_key(cols)
        except Exception:
            pass
    return ["entity_id"]


def compare_entity_diff(
    runs_dir: Path,
    run_ids: list[str],
    stage_path: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> EntityDiffPage:
    if len(run_ids) < 2:
        return EntityDiffPage(
            run_ids=run_ids,
            stage_path=stage_path,
            error="Entity diff requires at least two runs",
        )

    frames: dict[str, pd.DataFrame] = {}
    key_sets: list[list[str]] = []
    for run_id in run_ids:
        stage_dir = resolve_stage_dir(resolve_run_dir(runs_dir, run_id), stage_path)
        if stage_dir is None or not (stage_dir / "manifest.csv").exists():
            return EntityDiffPage(
                run_ids=run_ids,
                stage_path=stage_path,
                error=f"Missing manifest for {run_id} at {stage_path}",
            )
        df = pd.read_csv(stage_dir / "manifest.csv")
        frames[run_id] = df
        key_sets.append(_entity_key_columns(stage_dir))

    identity_warning = None
    base_keys = key_sets[0]
    if any(keys != base_keys for keys in key_sets[1:]):
        identity_warning = "Identity keys differ across runs — falling back to row-index comparison"
        base_keys = []

    left_id, right_id = run_ids[0], run_ids[1]
    left = frames[left_id].reset_index(drop=True)
    right = frames[right_id].reset_index(drop=True)

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    if base_keys and all(k in left.columns and k in right.columns for k in base_keys):
        left_keys = left[base_keys].fillna("").astype(str).agg("|".join, axis=1)
        right_keys = right[base_keys].fillna("").astype(str).agg("|".join, axis=1)
        left_index = set(left_keys)
        right_index = set(right_keys)

        for key in sorted(right_index - left_index):
            added.append(_row_dict(right.iloc[int(right_keys[right_keys == key].index[0])]))
        for key in sorted(left_index - right_index):
            removed.append(_row_dict(left.iloc[int(left_keys[left_keys == key].index[0])]))
        for key in sorted(left_index & right_index):
            lrow = left.iloc[int(left_keys[left_keys == key].index[0])]
            rrow = right.iloc[int(right_keys[right_keys == key].index[0])]
            delta = {}
            for col in sorted(set(lrow.index) | set(rrow.index)):
                lv, rv = lrow.get(col), rrow.get(col)
                if pd.isna(lv) and pd.isna(rv):
                    continue
                if str(lv) != str(rv):
                    delta[col] = {"left": lv, "right": rv}
            if delta:
                changed.append({"entity_key": key, "changes": delta})
    else:
        max_len = max(len(left), len(right))
        for idx in range(max_len):
            if idx >= len(left):
                added.append(_row_dict(right.iloc[idx]))
            elif idx >= len(right):
                removed.append(_row_dict(left.iloc[idx]))
            else:
                lrow, rrow = left.iloc[idx], right.iloc[idx]
                delta = {}
                for col in sorted(set(lrow.index) | set(rrow.index)):
                    lv, rv = lrow.get(col), rrow.get(col)
                    if pd.isna(lv) and pd.isna(rv):
                        continue
                    if str(lv) != str(rv):
                        delta[col] = {"left": lv, "right": rv}
                if delta:
                    changed.append({"row_index": idx, "changes": delta})

    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    start = (page - 1) * page_size

    combined: list[dict[str, Any]] = []
    combined += [{"kind": "added", **row} for row in added]
    combined += [{"kind": "removed", **row} for row in removed]
    combined += [{"kind": "changed", **row} for row in changed]
    total_items = len(combined)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page_rows = combined[start : start + page_size]

    return EntityDiffPage(
        run_ids=run_ids,
        stage_path=stage_path,
        items=page_rows,
        added=[r for r in page_rows if r.get("kind") == "added"],
        removed=[r for r in page_rows if r.get("kind") == "removed"],
        changed=[r for r in page_rows if r.get("kind") == "changed"],
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        identity_warning=identity_warning,
    )


def compare_ledgers(runs_dir: Path, run_ids: list[str]) -> LedgerCompare:
    rows_by_stage: dict[str, LedgerCompareRow] = {}
    for run_id in run_ids:
        timeline = load_ledger_timeline(runs_dir, run_id)
        for entry in timeline.entries:
            row = rows_by_stage.setdefault(
                entry.stage_path,
                LedgerCompareRow(stage_path=entry.stage_path, per_run={}),
            )
            row.per_run[run_id] = {
                "output_hash": entry.output_hash,
                "params_hash": entry.params_hash,
                "arming_hash": entry.arming_hash,
                "status": entry.status,
                "timestamp": entry.timestamp,
            }
        hashes = {
            run_id: row.per_run[run_id]["output_hash"]
            for run_id in run_ids
            if run_id in row.per_run and row.per_run[run_id].get("output_hash")
        }
        row.hash_mismatch = len(set(hashes.values())) > 1 if len(hashes) >= 2 else False
    return LedgerCompare(run_ids=run_ids, rows=sorted(rows_by_stage.values(), key=lambda r: r.stage_path))


def export_comparison_report(runs_dir: Path, request: ExportRequest) -> str:
    run_meta = []
    for run_id in request.run_ids:
        detail = get_run(runs_dir, run_id)
        run_meta.append(
            {
                "run_id": run_id,
                "started_at": detail.started_at if detail else None,
                "status": detail.status if detail else "unknown",
            }
        )

    payload: dict[str, Any] = {
        "run_ids": request.run_ids,
        "runs": run_meta,
        "sections": request.sections,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
    }

    if "config" in request.sections:
        payload["config"] = compare_configs(runs_dir, request.run_ids).model_dump()
    if "manifest_summary" in request.sections:
        payload["manifest_summary"] = compare_manifest_summaries(runs_dir, request.run_ids).model_dump()
    if "entity_diff" in request.sections and request.stage_path:
        payload["entity_diff"] = compare_entity_diff(
            runs_dir, request.run_ids, request.stage_path
        ).model_dump()
    elif "entity_diff" in request.sections:
        payload["entity_diff"] = {"unavailable": "stage_path required for entity diff export"}
    if "ledger" in request.sections:
        payload["ledger"] = compare_ledgers(runs_dir, request.run_ids).model_dump()

    if request.format == "json":
        return json.dumps(payload, indent=2, default=str)

    lines = [
        "# Plinth run comparison report",
        "",
        f"**Runs:** {', '.join(request.run_ids)}",
        f"**Sections:** {', '.join(request.sections)}",
        "",
        "## Run metadata",
    ]
    for meta in run_meta:
        lines.append(f"- **{meta['run_id']}:** {meta['status']} · {meta['started_at'] or 'unknown start'}")
    lines.append("")

    if "config" in payload:
        lines.append("## Config diff")
        cfg = payload["config"]
        if cfg.get("unavailable"):
            lines.append(f"Unavailable config snapshots: {', '.join(cfg['unavailable'])}")
        for diff in cfg.get("structural_diffs", []):
            lines.append(f"- `{diff['path']}` ({diff.get('change', 'changed')})")
        for section in cfg.get("sections", []):
            lines.append(f"### {section['run_id']}")
            lines.append("```yaml")
            lines.append(yaml.dump(section.get("config", {}), sort_keys=False))
            lines.append("```")
        lines.append("")
    if "manifest_summary" in payload:
        lines.append("## Manifest summary")
        for row in payload["manifest_summary"].get("rows", []):
            lines.append(f"### {row['stage_path']}")
            for run_id, summary in row.get("per_run", {}).items():
                if summary.get("unavailable"):
                    lines.append(f"- **{run_id}:** unavailable")
                else:
                    lines.append(
                        f"- **{run_id}:** {summary.get('row_count', '?')} rows, "
                        f"{len(summary.get('columns', []))} columns"
                    )
        lines.append("")
    if "ledger" in payload:
        lines.append("## Ledger comparison")
        for row in payload["ledger"].get("rows", []):
            lines.append(f"### {row['stage_path']}")
            for run_id, summary in row.get("per_run", {}).items():
                lines.append(
                    f"- **{run_id}:** hash `{summary.get('output_hash', '')[:12]}…` "
                    f"({summary.get('status')})"
                )
        lines.append("")
    return "\n".join(lines)
