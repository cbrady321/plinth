"""Filesystem artifact browser."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from plinth.researcher_ui.models import ArtifactNode, ArtifactTree
from plinth.researcher_ui.services.run_index import CONFIG_SNAPSHOT, resolve_run_dir
from plinth.stage_directory import StageDirectoryManager

INLINE_PREVIEW_LIMIT = 256 * 1024
MANIFEST_NAMES = frozenset({"manifest.csv"})
SCHEMA_NAMES = frozenset({"dataset_schema.yaml", "schema.yaml"})


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _load_export_flags(run_dir: Path) -> dict[str, bool]:
    config_path = run_dir / CONFIG_SNAPSHOT
    if not config_path.exists():
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    flags = data.get("export_flags") or {}
    return {str(key): bool(value) for key, value in flags.items()}


def _stage_export_annotation(
    run_dir: Path, dir_name: str, export_flags: dict[str, bool]
) -> tuple[str | None, str | None]:
    parsed = StageDirectoryManager.parse_directory_name(dir_name)
    if not parsed:
        return None, None
    _, stage_name = parsed
    if not export_flags.get(stage_name):
        return None, None
    export_path = run_dir / "export" / dir_name
    if export_path.is_dir():
        return "export enabled", None
    return None, "export enabled but export tree missing"


def _build_tree(path: Path, run_dir: Path, export_flags: dict[str, bool]) -> ArtifactNode:
    rel = str(path.relative_to(run_dir))
    if path.is_dir():
        export_label, export_warning = _stage_export_annotation(run_dir, path.name, export_flags)
        children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        return ArtifactNode(
            name=path.name,
            path=rel,
            kind="directory",
            export_label=export_label,
            export_warning=export_warning,
            children=[_build_tree(child, run_dir, export_flags) for child in children],
        )

    stat = path.stat()
    return ArtifactNode(
        name=path.name,
        path=rel,
        kind="file",
        size_bytes=stat.st_size,
        modified_at=_iso(stat.st_mtime),
        manifest_link=path.name in MANIFEST_NAMES or path.name in SCHEMA_NAMES,
    )


def load_artifact_tree(runs_dir: Path, run_id: str) -> ArtifactTree:
    run_dir = resolve_run_dir(runs_dir, run_id)
    if run_dir is None:
        return ArtifactTree(
            run_id=run_id,
            root=ArtifactNode(name=run_id, path=".", kind="directory", children=[]),
            error=f"Run not found: {run_id}",
        )

    export_flags = _load_export_flags(run_dir)
    root = _build_tree(run_dir, run_dir, export_flags)
    return ArtifactTree(run_id=run_id, root=root)


def resolve_artifact_path(runs_dir: Path, run_id: str, relative_path: str) -> Path | None:
    run_dir = resolve_run_dir(runs_dir, run_id)
    if run_dir is None:
        return None
    candidate = (run_dir / relative_path).resolve()
    if not candidate.is_relative_to(run_dir) or not candidate.is_file():
        return None
    return candidate
