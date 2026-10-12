"""DAG construction helpers extracted from blocks.py."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from plinth.blocks import Block


@dataclass
class BlockExecutionResult:
    output_dirs: List[Path]
    block_name: str
    block_type: str

    def get_single_output(self) -> Path:
        if len(self.output_dirs) != 1:
            raise ValueError(f"Expected single output, got {len(self.output_dirs)}")
        return self.output_dirs[0]


class ExecutionConstraints:
    def __init__(
        self,
        end_index_paths: Optional[List[List[int]]] = None,
        start_index_path: Optional[List[int]] = None,
    ):
        self._end_index_paths: List[List[int]] = end_index_paths or []
        self._start_index_path: Optional[List[int]] = start_index_path

    def has_any_end_paths(self) -> bool:
        return len(self._end_index_paths) > 0

    def is_end_here(self, current_index_path: List[int]) -> bool:
        return any(path == current_index_path for path in self._end_index_paths)

    def is_relevant_subtree(self, current_index_path: List[int]) -> bool:
        for path in self._end_index_paths:
            if len(path) >= len(current_index_path) and path[: len(current_index_path)] == current_index_path:
                return True
        return False

    def is_before_start(self, current_index_path: List[int]) -> bool:
        if not self._start_index_path:
            return False

        for i in range(min(len(current_index_path), len(self._start_index_path))):
            if current_index_path[i] < self._start_index_path[i]:
                return True
            if current_index_path[i] > self._start_index_path[i]:
                return False

        return False


def build_dag_from_dict(dag_dict: Dict[str, Any], config: Dict[str, Any], path: str = "dag") -> Block:
    """Build a block tree; structural mistakes raise ``ValueError`` naming the offending node's path."""
    from plinth.blocks import ParallelBlock, SequentialBlock, StageNode

    if not isinstance(dag_dict, dict):
        raise ValueError(f"{path}: expected a mapping with 'type' and 'name', got {type(dag_dict).__name__}")
    block_type = dag_dict.get("type")
    name = dag_dict.get("name")
    if block_type is None:
        raise ValueError(f"{path}: missing 'type' (one of: stage, sequential, parallel)")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{path}: {block_type} block is missing a 'name'")

    if block_type == "stage":
        return StageNode(name, config)
    if block_type not in ("sequential", "parallel"):
        raise ValueError(f"{path}: Unknown block type: {block_type} (expected stage, sequential or parallel)")

    child_dicts = dag_dict.get("children", [])
    if not isinstance(child_dicts, list):
        raise ValueError(f"{path}: 'children' of {block_type} block '{name}' must be a list")
    children = [
        build_dag_from_dict(child_dict, config, f"{path}.children[{index}]")
        for index, child_dict in enumerate(child_dicts)
    ]

    if block_type == "sequential":
        return SequentialBlock(name, config, children)
    return ParallelBlock(name, config, children)
