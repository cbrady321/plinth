"""Hypothesis properties for address resolver on random sequential DAGs."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from plinth.address.resolver import NodeAddressResolver
from plinth.blocks import build_dag_from_dict


@pytest.mark.property
@given(stage_count=st.integers(min_value=1, max_value=6))
def test_sequential_noop_dag_directory_names_unique(stage_count: int) -> None:
    children = [{"type": "stage", "name": f"noop_{i}"} for i in range(stage_count)]
    dag = {"type": "sequential", "name": "root", "children": children}
    config_dict = {
        "params": {f"noop_{i}": {} for i in range(stage_count)},
        "name": "root",
        "version": "1",
    }
    dag_root = build_dag_from_dict(dag, config_dict)
    resolver = NodeAddressResolver()

    names: list[str] = []
    for idx in range(stage_count):
        address = resolver.resolve_at_index_path(dag_root, [idx], config_dict)
        names.append(address.directory_name)
        assert address.directory_name.endswith(f"noop_{idx}")

    assert len(set(names)) == stage_count
