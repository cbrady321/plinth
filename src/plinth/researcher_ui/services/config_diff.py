"""Structural config diff helpers."""

from __future__ import annotations

from typing import Any


def _json_paths(obj: Any, prefix: str = "$") -> dict[str, Any]:
    paths: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix != "$" else f"$.{key}"
            paths.update(_json_paths(value, child))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            paths.update(_json_paths(value, f"{prefix}[{index}]"))
    else:
        paths[prefix] = obj
    return paths


def diff_configs(configs: list[dict[str, Any]], run_ids: list[str]) -> list[dict[str, Any]]:
    """Return added/removed/changed JSONPath entries across configs."""
    if len(configs) < 2:
        return []

    path_maps = [_json_paths(config) for config in configs]
    all_paths = sorted(set().union(*(m.keys() for m in path_maps)))
    diffs: list[dict[str, Any]] = []

    for path in all_paths:
        values = [path_map.get(path, "__MISSING__") for path_map in path_maps]
        unique = {repr(v) for v in values}
        if len(unique) == 1:
            continue
        entry: dict[str, Any] = {"path": path, "per_run": {}}
        for run_id, value in zip(run_ids, values):
            if value == "__MISSING__":
                entry["per_run"][run_id] = {"status": "removed"}
            else:
                entry["per_run"][run_id] = value
        if all(v == "__MISSING__" for v in values[:-1]) and values[-1] != "__MISSING__":
            entry["change"] = "added"
        elif values[0] != "__MISSING__" and any(v == "__MISSING__" for v in values[1:]):
            entry["change"] = "removed"
        else:
            entry["change"] = "changed"
        diffs.append(entry)
    return diffs
