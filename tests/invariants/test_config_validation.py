"""Pipeline config validation tests."""

from __future__ import annotations

from plinth.config import PipelineConfig


def test_validate_rejects_unknown_stage() -> None:
    config = PipelineConfig(
        name="bad",
        version="1",
        dag={
            "type": "sequential",
            "name": "root",
            "children": [{"type": "stage", "name": "not_a_real_stage"}],
        },
        params={},
    )
    result = config.validate()
    assert not result.ok
    assert any("not_a_real_stage" in err for err in result.errors)


def test_validate_accepts_golden_config() -> None:
    from pathlib import Path

    config = PipelineConfig.from_yaml(
        Path("tests/fixtures/golden_pipeline/config.yaml")
    )
    result = config.validate()
    assert result.ok, result.errors


def test_validate_rejects_parallel_write_conflict() -> None:
    config = PipelineConfig(
        name="conflict",
        version="1",
        dag={
            "type": "parallel",
            "name": "par",
            "children": [
                {"type": "stage", "name": "tag_category"},
                {"type": "stage", "name": "tag_category"},
            ],
        },
        params={},
    )
    result = config.validate()
    assert not result.ok
    assert any("parallel conflict" in err for err in result.errors)


def test_validate_reports_unknown_stage_inside_parallel_block() -> None:
    config = PipelineConfig(
        name="bad",
        version="1",
        dag={
            "type": "sequential",
            "name": "root",
            "children": [
                {
                    "type": "parallel",
                    "name": "par",
                    "children": [
                        {"type": "stage", "name": "not_a_real_stage"},
                        {"type": "stage", "name": "another_missing_stage"},
                    ],
                }
            ],
        },
    )
    result = config.validate()
    assert not result.ok
    assert "stage 'not_a_real_stage' is not registered" in result.errors
    assert "stage 'another_missing_stage' is not registered" in result.errors


def test_validate_names_the_malformed_dag_node() -> None:
    cases = {
        "dag.children[1]: stage block is missing a 'name'": {
            "type": "sequential",
            "name": "root",
            "children": [{"type": "stage", "name": "a"}, {"type": "stage"}],
        },
        "dag: missing 'type'": {"name": "root", "children": []},
        "dag.children[0]: Unknown block type: loop": {
            "type": "sequential",
            "name": "root",
            "children": [{"type": "loop", "name": "x"}],
        },
        "dag: 'children' of sequential block 'root' must be a list": {
            "type": "sequential",
            "name": "root",
            "children": {"type": "stage", "name": "a"},
        },
    }
    for expected, dag in cases.items():
        result = PipelineConfig(name="bad", version="1", dag=dag).validate()
        assert not result.ok
        assert any(err.startswith(expected) for err in result.errors), (expected, result.errors)
