"""Dataclasses for DAG configuration to simplify pipeline setup."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from plinth.blocks import Block, build_dag_from_dict


@dataclass
class StageConfig:
    """Configuration for a single stage in the DAG."""

    name: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for build_dag_from_dict."""
        return {"type": "stage", "name": self.name}


@dataclass
class SequentialBlockConfig:
    """Configuration for a sequential block containing stages or other blocks."""

    name: str
    children: Sequence[Union["StageConfig", "SequentialBlockConfig", "ParallelBlockConfig"]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for build_dag_from_dict."""
        return {"type": "sequential", "name": self.name, "children": [child.to_dict() for child in self.children]}


@dataclass
class ParallelBlockConfig:
    """Configuration for a parallel block containing stages or other blocks."""

    name: str
    children: Sequence[Union["StageConfig", "SequentialBlockConfig", "ParallelBlockConfig"]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for build_dag_from_dict."""
        return {"type": "parallel", "name": self.name, "children": [child.to_dict() for child in self.children]}


@dataclass
class DAGConfig:
    """Complete DAG configuration with root block and parameters."""

    root: Union[SequentialBlockConfig, ParallelBlockConfig]
    params: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for build_dag_from_dict."""
        return self.root.to_dict()

    def build_block_tree(self, pipeline_config: Dict[str, Any]) -> Block:
        """
        Build the complete block tree from this DAG configuration.

        Args:
            pipeline_config: Pipeline configuration dict (for params, export_flags, etc.)

        Returns:
            Root Block instance ready for execution
        """
        # Merge DAG params with pipeline config
        config_dict = {
            "params": {**pipeline_config.get("params", {}), **self.params},
            "export_flags": pipeline_config.get("export_flags", {}),
            "name": pipeline_config.get("name", "pipeline"),
            "version": pipeline_config.get("version", "1.0"),
        }

        return build_dag_from_dict(self.to_dict(), config_dict)

    def get_all_stage_names(self) -> List[str]:
        """Get flattened list of all stage names in the DAG."""
        return self._extract_stage_names(self.root)

    def _extract_stage_names(self, block: Union[StageConfig, SequentialBlockConfig, ParallelBlockConfig]) -> List[str]:
        """Recursively extract stage names from block structure."""
        if isinstance(block, StageConfig):
            return [block.name]

        names = []
        for child in block.children:
            names.extend(self._extract_stage_names(child))
        return names


# Type aliases for cleaner type hints
BlockConfig = Union[StageConfig, SequentialBlockConfig, ParallelBlockConfig]


def create_simple_sequential_pipeline(
    name: str, stages: List[str], params: Optional[Dict[str, Dict[str, Any]]] = None
) -> DAGConfig:
    """
    Create a simple sequential pipeline from a list of stage names.

    Args:
        name: Name of the root block
        stages: List of stage names in execution order
        params: Optional parameters for stages

    Returns:
        DAGConfig for a sequential pipeline

    Example:
        config = create_simple_sequential_pipeline(
            "prepare",
            ["load", "clean", "split"],
            {"clean": {"drop_empty": True}}
        )
    """
    stage_configs = [StageConfig(stage_name) for stage_name in stages]
    root = SequentialBlockConfig(name=name, children=stage_configs)
    return DAGConfig(root=root, params=params or {})


def create_fan_out_pipeline(
    before: List[str],
    parallel: List[str],
    after: List[str],
    params: Optional[Dict[str, Dict[str, Any]]] = None,
) -> DAGConfig:
    """
    Create a pipeline that runs sequential stages, then parallel branches, then sequential stages.

    Args:
        before: Sequential stages before the parallel block (block ``before``)
        parallel: Stages run as parallel branches (block ``fan_out``)
        after: Sequential stages after the parallel block (block ``after``)
        params: Optional parameters for stages

    Returns:
        DAGConfig with before → parallel → after; empty groups are omitted

    Example:
        config = create_fan_out_pipeline(
            before=["load", "clean"],
            parallel=["branch_a", "branch_b", "branch_c"],
            after=["merge", "report"]
        )
    """
    children: List[Union[SequentialBlockConfig, ParallelBlockConfig]] = []
    if before:
        children.append(SequentialBlockConfig(name="before", children=[StageConfig(stage) for stage in before]))
    if parallel:
        children.append(ParallelBlockConfig(name="fan_out", children=[StageConfig(stage) for stage in parallel]))
    if after:
        children.append(SequentialBlockConfig(name="after", children=[StageConfig(stage) for stage in after]))

    root = SequentialBlockConfig(name="root", children=children)
    return DAGConfig(root=root, params=params or {})


def create_nested_parallel_pipeline(
    main_blocks: List[Union[SequentialBlockConfig, ParallelBlockConfig]],
    params: Optional[Dict[str, Dict[str, Any]]] = None,
) -> DAGConfig:
    """
    Create a pipeline with nested parallel and sequential blocks.

    Args:
        main_blocks: List of block configurations for the main pipeline
        params: Optional parameters for stages

    Returns:
        DAGConfig with the specified block structure

    Example:
        prepare = SequentialBlockConfig(
            name="prepare",
            children=[StageConfig("load"), StageConfig("clean")]
        )

        branches = ParallelBlockConfig(
            name="branches",
            children=[StageConfig("branch_a"), StageConfig("branch_b")]
        )

        config = create_nested_parallel_pipeline([prepare, branches])
    """
    root = SequentialBlockConfig(name="root", children=main_blocks)
    return DAGConfig(root=root, params=params or {})
