"""Property tests: execute and cleanup agree on directory names."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from plinth.address.resolver import NodeAddressResolver
from plinth.blocks import ParallelBlock, StageNode, build_dag_from_dict
from plinth.config import PipelineConfig


@pytest.mark.parametrize(
    "dag,config_path,index_path,expected_dir",
    [
        (
            {
                "type": "sequential",
                "name": "root",
                "children": [{"type": "stage", "name": "allowlist_filter"}],
            },
            "tests/fixtures/golden_pipeline/config.yaml",
            [0],
            "02_allowlist_filter",
        ),
        (
            {
                "type": "sequential",
                "name": "root",
                "children": [
                    {"type": "stage", "name": "stage_a"},
                    {"type": "stage", "name": "stage_b"},
                ],
            },
            None,
            [1],
            "03_stage_b",
        ),
    ],
)
def test_resolver_matches_execute_directory_names(
    dag: dict,
    config_path: str | None,
    index_path: list[int],
    expected_dir: str,
) -> None:
    if config_path:
        cfg = PipelineConfig.from_yaml(Path(config_path))
        config_dict = {
            "params": cfg.params,
            "export_flags": cfg.export_flags,
            "_block_settings": cfg.block_settings,
            "name": cfg.name,
            "version": cfg.version,
            "always_propagate": cfg.always_propagate,
            "parallel_error_policy": cfg.parallel_error_policy,
        }
        dag_root = cfg.build_dag()
    else:
        config_dict = {"params": {"stage_a": {}, "stage_b": {}}, "name": "root", "version": "1"}
        dag_root = build_dag_from_dict(dag, config_dict)

    resolver = NodeAddressResolver()
    address = resolver.resolve_at_index_path(dag_root, index_path, config_dict)
    assert address.directory_name == expected_dir


def test_cleanup_child_prefix_parallel_parent() -> None:
    resolver = NodeAddressResolver()
    parent = ParallelBlock("par", {}, [])
    child = StageNode("leaf", {"params": {}})
    assert resolver.child_prefix_for_cleanup(parent, child, 2) == "c"


@given(stage_count=st.integers(min_value=1, max_value=5))
def test_sequential_stage_directory_names_are_deterministic(stage_count: int) -> None:
    children = [{"type": "stage", "name": f"s{i}"} for i in range(stage_count)]
    dag = {"type": "sequential", "name": "root", "children": children}
    config_dict = {"params": {f"s{i}": {} for i in range(stage_count)}, "name": "root", "version": "1"}
    dag_root = build_dag_from_dict(dag, config_dict)
    resolver = NodeAddressResolver()

    names: list[str] = []
    for idx in range(stage_count):
        address = resolver.resolve_at_index_path(dag_root, [idx], config_dict)
        names.append(address.directory_name)
        assert address.directory_name.endswith(f"s{idx}")

    assert len(set(names)) == stage_count
