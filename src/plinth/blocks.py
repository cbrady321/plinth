"""Block abstraction for DAG-based pipeline execution."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from plinth.address.codes import build_location_code
from plinth.block_dag import BlockExecutionResult, ExecutionConstraints, build_dag_from_dict
from plinth.registry import StageRegistry

__all__ = [
    "Block",
    "BlockExecutionResult",
    "ExecutionConstraints",
    "ParallelBlock",
    "SequentialBlock",
    "StageNode",
    "build_dag_from_dict",
]


class Block(ABC):
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.children: List[Block] = []

    @abstractmethod
    def execute(
        self,
        input_dirs: List[Path],
        parent_output_dir: Path,
        prefix: Optional[Union[int, str]],
        constraints: Optional[ExecutionConstraints] = None,
        current_index_path: Optional[List[int]] = None,
        parent_location_code: str = "",
        sequential_counter: Optional[List[int]] = None,
    ) -> BlockExecutionResult:
        pass

    @abstractmethod
    def get_all_stage_names(self) -> List[str]:
        pass

    @abstractmethod
    def get_written_columns(self) -> Set[str]:
        pass

    @abstractmethod
    def get_unique_key_modifications(self) -> Set[str]:
        pass

    def find_path_to_stage(self, stage_name: str, current_path: Optional[List[int]] = None) -> Optional[List[int]]:
        if current_path is None:
            current_path = []

        if self.name == stage_name:
            return current_path

        for i, child in enumerate(self.children):
            child_path = current_path + [i]
            result = child.find_path_to_stage(stage_name, child_path)
            if result is not None:
                return result
        return None

    def find_node_by_name(self, name: str) -> Optional["Block"]:
        if self.name == name:
            return self
        for child in self.children:
            result = child.find_node_by_name(name)
            if result:
                return result
        return None

    def find_node_by_path(self, path: List[int]) -> Optional["Block"]:
        if not path:
            return self
        if path[0] >= len(self.children):
            return None
        child = self.children[path[0]]
        return child.find_node_by_path(path[1:])

    def _build_location_code(self, prefix: Union[int, str], parent_code: str = "") -> str:
        return build_location_code(prefix, parent_code)

    def _get_block_setting(self, key: str, default: Any) -> Any:
        settings = self.config.get("_block_settings", {})
        if not isinstance(settings, dict):
            return default
        block_settings = settings.get(self.name, {})
        if not isinstance(block_settings, dict):
            return default
        return block_settings.get(key, default)

    def get_block_directory_name(self, prefix: Union[int, str], location_code: Optional[str] = None) -> str:
        if location_code is not None:
            return f"{location_code}_{self.name}"
        if isinstance(prefix, int):
            return f"{prefix:02d}_{self.name}"
        return f"{prefix}_{self.name}"


class SequentialBlock(Block):
    def __init__(self, name: str, config: Dict[str, Any], children: List[Block]):
        super().__init__(name, config)
        self.children = children

    def execute(
        self,
        input_dirs: List[Path],
        parent_output_dir: Path,
        prefix: Optional[Union[int, str]],
        constraints: Optional[ExecutionConstraints] = None,
        current_index_path: Optional[List[int]] = None,
        parent_location_code: str = "",
        sequential_counter: Optional[List[int]] = None,
    ) -> BlockExecutionResult:
        from plinth.block_executors import execute_sequential_block

        return execute_sequential_block(
            self,
            input_dirs,
            parent_output_dir,
            prefix,
            constraints,
            current_index_path,
            parent_location_code,
            sequential_counter,
        )

    def get_all_stage_names(self) -> List[str]:
        return [name for child in self.children for name in child.get_all_stage_names()]

    def get_written_columns(self) -> Set[str]:
        return {col for child in self.children for col in child.get_written_columns()}

    def get_unique_key_modifications(self) -> Set[str]:
        return {col for child in self.children for col in child.get_unique_key_modifications()}


class ParallelBlock(Block):
    def __init__(self, name: str, config: Dict[str, Any], children: List[Block]):
        super().__init__(name, config)
        self.children = children

    def execute(
        self,
        input_dirs: List[Path],
        parent_output_dir: Path,
        prefix: Optional[Union[int, str]],
        constraints: Optional[ExecutionConstraints] = None,
        current_index_path: Optional[List[int]] = None,
        parent_location_code: str = "",
        sequential_counter: Optional[List[int]] = None,
    ) -> BlockExecutionResult:
        from plinth.block_executors import execute_parallel_block

        return execute_parallel_block(
            self,
            input_dirs,
            parent_output_dir,
            prefix,
            constraints,
            current_index_path,
            parent_location_code,
            sequential_counter,
        )

    def get_all_stage_names(self) -> List[str]:
        return [name for child in self.children for name in child.get_all_stage_names()]

    def get_written_columns(self) -> Set[str]:
        return {col for child in self.children for col in child.get_written_columns()}

    def get_unique_key_modifications(self) -> Set[str]:
        return {col for child in self.children for col in child.get_unique_key_modifications()}


class StageNode(Block):
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._stage: Any = None

    def _get_stage(self) -> Any:
        if self._stage is None:
            stage_class = StageRegistry.get_stage(self.name)
            stage_params = self.config.get("params", {}).get(self.name, {})

            if "always_propagate" in self.config:
                stage_params["_always_propagate"] = self.config["always_propagate"]

            self._stage = stage_class(stage_name=self.name, config=stage_params)
            if StageRegistry.get_mode(self.name) == "typical":
                self._stage.get_intent().validate_strict()
        return self._stage

    def execute(
        self,
        input_dirs: List[Path],
        parent_output_dir: Path,
        prefix: Optional[Union[int, str]],
        constraints: Optional[ExecutionConstraints] = None,
        current_index_path: Optional[List[int]] = None,
        parent_location_code: str = "",
        sequential_counter: Optional[List[int]] = None,
    ) -> BlockExecutionResult:
        from plinth.block_executors import execute_stage_node

        return execute_stage_node(
            self,
            input_dirs,
            parent_output_dir,
            prefix,
            constraints,
            current_index_path,
            parent_location_code,
            sequential_counter,
        )

    def get_all_stage_names(self) -> List[str]:
        return [self.name]

    def get_written_columns(self) -> Set[str]:
        stage = self._get_stage()
        if not hasattr(stage, "get_intent"):
            return set()
        intent = stage.get_intent()
        return set(intent.write_columns.keys()) | set(intent.modify_columns)

    def get_unique_key_modifications(self) -> Set[str]:
        stage = self._get_stage()
        if not hasattr(stage, "get_intent"):
            return set()
        intent = stage.get_intent()
        return set(intent.append_to_unique_key)
