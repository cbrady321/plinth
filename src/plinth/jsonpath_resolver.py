"""Lightweight JSONPath resolver for DAG node selection.

Supported subset:
- Absolute paths starting with $.<root_name>
- children[index] chains, where index can be a single int or comma list: children[0,2]

Examples:
- $.root.children[1].children[0] -> one path
- $.root.children[1].children[0,2] -> two paths
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from plinth.blocks import Block


def expand_jsonpath_indices(path: str) -> List[str]:
    """Expand JSONPath with comma-separated indices into multiple concrete paths.

    E.g., $.root.children[1].children[0,2] -> [$.root.children[1].children[0], $.root.children[1].children[2]]
    """
    segments: List[str] = []
    i = 0
    while i < len(path):
        if path.startswith("children[", i):
            # read until closing ]
            start = i + len("children[")
            end = path.find("]", start)
            if end == -1:
                raise ValueError("Malformed JSONPath: missing closing bracket")
            indices = path[start:end]
            segments.append(f"children[{indices}]")
            i = end + 1
        else:
            # copy next char
            segments.append(path[i])
            i += 1

    # Rejoin into a normalized representation
    normalized = "".join(segments)

    # Now split on segments that have comma separated indices
    def split_once(paths: List[str]) -> List[str]:
        out: List[str] = []
        for p in paths:
            start = p.find("children[")
            while start != -1:
                end = p.find("]", start)
                idx_segment = p[start + len("children[") : end]
                if "," in idx_segment:
                    left = p[:start]
                    right = p[end + 1 :]
                    for idx_str in [s.strip() for s in idx_segment.split(",") if s.strip()]:
                        out.append(f"{left}children[{idx_str}]{right}")
                    break
                else:
                    start = p.find("children[", end)
            else:
                out.append(p)
        return out

    # Iteratively expand until no comma lists remain
    current = [normalized]
    while True:
        expanded = split_once(current)
        if expanded == current:
            return expanded
        current = expanded


def path_to_index_list(path: str, root_name: str) -> List[int]:
    """Convert a concrete JSONPath like $.root.children[1].children[0] to index list [1,0]."""
    if not path.startswith(f"$.{root_name}"):
        raise ValueError("Path must start with root name")
    idxs: List[int] = []
    i = len(f"$.{root_name}")
    while i < len(path):
        if path.startswith(".children[", i) or path.startswith("children[", i):
            start = path.find("[", i) + 1
            end = path.find("]", start)
            if end == -1:
                raise ValueError("Malformed children index")
            idxs.append(int(path[start:end]))
            i = end + 1
        elif path[i] == ".":
            i += 1
        else:
            # ignore other chars (like stray dots)
            i += 1
    return idxs


def resolve_index_path(dag_root: Block, index_path: List[int]) -> Block:
    """Resolve a DAG child-index path to the target block; raise if out of range."""
    node = dag_root.find_node_by_path(index_path)
    if node is None:
        raise ValueError(
            f"JSONPath index path {index_path} is out of range for DAG "
            f"'{dag_root.name}' (author contract §JSONPath skip and resume): no node at path"
        )
    return node
