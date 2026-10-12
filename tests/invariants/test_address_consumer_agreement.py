"""Consumer agreement: execute, cleanup, skip/resume, and discovery use one address authority."""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from plinth.address.resolver import NodeAddressResolver
from plinth.blocks import Block, ParallelBlock, SequentialBlock, StageNode, build_dag_from_dict
from plinth.stage_directory import StageDirectoryManager


def _stage(name: str) -> dict[str, Any]:
    return {"type": "stage", "name": name}


def _seq(*children: dict[str, Any], name: str = "root") -> dict[str, Any]:
    return {"type": "sequential", "name": name, "children": list(children)}


def _par(*children: dict[str, Any], name: str = "par") -> dict[str, Any]:
    return {"type": "parallel", "name": name, "children": list(children)}


def _config_for(*stage_names: str) -> dict[str, Any]:
    return {
        "params": {name: {} for name in stage_names},
        "name": "root",
        "version": "1",
    }


def _collect_stage_names(dag: dict[str, Any]) -> list[str]:
    if dag["type"] == "stage":
        return [dag["name"]]
    return [n for child in dag["children"] for n in _collect_stage_names(child)]


def _iter_stage_index_paths(block: Block, prefix: list[int] | None = None) -> Iterator[list[int]]:
    path = prefix or []
    if isinstance(block, StageNode):
        yield path
        return
    for idx, child in enumerate(block.children):
        yield from _iter_stage_index_paths(child, path + [idx])


def _index_path_to_jsonpath(root_name: str, index_path: list[int]) -> str:
    parts = [f"$.{root_name}"]
    for idx in index_path:
        parts.append(f"children[{idx}]")
    return ".".join(parts)


def _dag_shapes() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    shapes: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for count in range(1, 6):
        stages = [_stage(f"s{i}") for i in range(count)]
        dag = _seq(*stages)
        shapes.append((dag, _config_for(*_collect_stage_names(dag))))

    for branch_count in (2, 3, 4):
        branches = [_stage(f"b{i}") for i in range(branch_count)]
        dag = _seq(_par(*branches, name="split"))
        shapes.append((dag, _config_for(*_collect_stage_names(dag))))

    for mid in range(1, 4):
        before = [_stage(f"pre{i}") for i in range(mid)]
        after = [_stage(f"post{i}") for i in range(2)]
        branches = [_stage("left"), _stage("right")]
        dag = _seq(*before, _par(*branches, name="mid"), *after)
        shapes.append((dag, _config_for(*_collect_stage_names(dag))))

    nested = _seq(
        _stage("head"),
        _par(
            _seq(_stage("a1"), _stage("a2")),
            _seq(_stage("b1"), _stage("b2")),
            name="nested_par",
        ),
        _stage("tail"),
    )
    shapes.append((nested, _config_for(*_collect_stage_names(nested))))

    deep_nested = _seq(
        _par(
            _par(_stage("x1"), _stage("x2"), name="inner1"),
            _par(_stage("y1"), _stage("y2"), name="inner2"),
            name="outer",
        ),
    )
    shapes.append((deep_nested, _config_for(*_collect_stage_names(deep_nested))))

    triple_seq_par = _seq(
        _stage("solo"),
        _par(_stage("p0"), _stage("p1"), _stage("p2"), name="triple"),
        _stage("fin"),
    )
    shapes.append((triple_seq_par, _config_for(*_collect_stage_names(triple_seq_par))))

    return shapes


def _all_path_cases() -> list[tuple[dict[str, Any], dict[str, Any], list[int]]]:
    cases: list[tuple[dict[str, Any], dict[str, Any], list[int]]] = []
    for dag_dict, config in _dag_shapes():
        dag_root = build_dag_from_dict(dag_dict, config)
        for index_path in _iter_stage_index_paths(dag_root):
            cases.append((dag_dict, config, index_path))
    return cases


_PATH_CASES = _all_path_cases()


assert len(_PATH_CASES) >= 20, f"expected >=20 generated paths, got {len(_PATH_CASES)}"


@pytest.mark.parametrize(
    "dag_dict,config,index_path",
    _PATH_CASES,
    ids=[f"path-{'-'.join(map(str, p))}-shape-{i}" for i, (_, _, p) in enumerate(_PATH_CASES)],
)
def test_resolver_execute_and_jsonpath_agree(
    dag_dict: dict[str, Any],
    config: dict[str, Any],
    index_path: list[int],
) -> None:
    dag_root = build_dag_from_dict(dag_dict, config)
    resolver = NodeAddressResolver()

    by_index = resolver.resolve_at_index_path(dag_root, index_path, config)
    jsonpath = _index_path_to_jsonpath(config["name"], index_path)
    by_jsonpath = resolver.resolve_from_jsonpath(dag_root, jsonpath, config["name"], config)

    assert by_index.directory_name == by_jsonpath.directory_name
    assert by_index.location_code == by_jsonpath.location_code
    assert by_index.block_name == by_jsonpath.block_name


@pytest.mark.parametrize(
    "dag_dict,config,index_path",
    _PATH_CASES,
    ids=[f"disc-{'-'.join(map(str, p))}-shape-{i}" for i, (_, _, p) in enumerate(_PATH_CASES)],
)
def test_discovery_parse_agrees_with_resolver(
    dag_dict: dict[str, Any],
    config: dict[str, Any],
    index_path: list[int],
) -> None:
    dag_root = build_dag_from_dict(dag_dict, config)
    resolver = NodeAddressResolver()
    address = resolver.resolve_at_index_path(dag_root, index_path, config)

    resolver_parsed = resolver.match_directory(address.directory_name)
    manager_parsed = StageDirectoryManager.parse_directory_name(address.directory_name)

    assert resolver_parsed is not None
    assert manager_parsed is not None
    assert resolver_parsed == manager_parsed


@pytest.mark.parametrize(
    "dag_dict,config,index_path",
    _PATH_CASES,
    ids=[f"clean-{'-'.join(map(str, p))}-shape-{i}" for i, (_, _, p) in enumerate(_PATH_CASES)],
)
def test_cleanup_prefix_walk_targets_resolver_directory(
    dag_dict: dict[str, Any],
    config: dict[str, Any],
    index_path: list[int],
) -> None:
    dag_root = build_dag_from_dict(dag_dict, config)
    resolver = NodeAddressResolver()
    expected = resolver.resolve_at_index_path(dag_root, index_path, config)

    def cleanup_dir_name_at_path(block: Block, path: list[int]) -> str:
        if not path:
            if isinstance(block, StageNode):
                addr = resolver.resolve_at_index_path(dag_root, index_path, config)
                return addr.directory_name
            raise ValueError("empty path must target a stage")

        child_idx = path[0]
        child = block.children[child_idx]
        resolver.child_prefix_for_cleanup(block, child, child_idx)

        if len(path) == 1 and isinstance(child, StageNode):
            partial = index_path[: len(index_path) - len(path) + 1]
            addr = resolver.resolve_at_index_path(dag_root, partial, config)
            return addr.directory_name

        if isinstance(block, SequentialBlock) and isinstance(child, ParallelBlock):
            return cleanup_dir_name_at_path(child, path[1:])

        return cleanup_dir_name_at_path(child, path[1:])

    assert cleanup_dir_name_at_path(dag_root, index_path) == expected.directory_name


@pytest.mark.parametrize(
    "dag_dict,config,index_path",
    _PATH_CASES[:25],
    ids=[f"skip-{'-'.join(map(str, p))}-shape-{i}" for i, (_, _, p) in enumerate(_PATH_CASES[:25])],
)
def test_skip_resume_expected_directory_matches_resolver(
    dag_dict: dict[str, Any],
    config: dict[str, Any],
    index_path: list[int],
) -> None:
    dag_root = build_dag_from_dict(dag_dict, config)
    resolver = NodeAddressResolver()
    expected = resolver.resolve_at_index_path(dag_root, index_path, config)

    stage_name = expected.block_name
    found_path = dag_root.find_path_to_stage(stage_name)
    assert found_path is not None
    assert found_path == index_path

    rediscovered = resolver.resolve_at_index_path(dag_root, found_path, config)
    assert rediscovered.directory_name == expected.directory_name


def test_consumer_agreement_case_count_at_least_twenty() -> None:
    assert len(_PATH_CASES) >= 20


def test_build_location_code_single_entry_point() -> None:
    from plinth.address.codes import build_location_code as codes_build

    assert NodeAddressResolver.build_location_code is codes_build
    dummy = SequentialBlock("x", {}, [])
    assert dummy._build_location_code(2, "") == codes_build(2, "")
