"""Tests for NodeAddressResolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.address.resolver import NodeAddressResolver
from plinth.config import PipelineConfig


@pytest.fixture
def golden_config() -> PipelineConfig:
    return PipelineConfig.from_yaml(
        Path("tests/fixtures/golden_pipeline/config.yaml")
    )


def test_golden_pipeline_directory_matches_execute(golden_config: PipelineConfig) -> None:
    dag_root = golden_config.build_dag()
    resolver = NodeAddressResolver()
    config_dict = {
        "params": golden_config.params,
        "export_flags": golden_config.export_flags,
        "_block_settings": golden_config.block_settings,
        "name": golden_config.name,
        "version": golden_config.version,
        "always_propagate": golden_config.always_propagate,
        "parallel_error_policy": golden_config.parallel_error_policy,
    }
    address = resolver.resolve_at_index_path(dag_root, [0], config_dict)
    assert address.directory_name == "02_allowlist_filter"


def test_build_location_code_int_prefix() -> None:
    resolver = NodeAddressResolver()
    assert resolver.build_location_code(6, "06a") == "06a06"


def test_build_location_code_str_prefix() -> None:
    resolver = NodeAddressResolver()
    assert resolver.build_location_code("a", "06") == "06a"


def test_match_directory_parses_location_code() -> None:
    resolver = NodeAddressResolver()
    parsed = resolver.match_directory("06a01_tag_category")
    assert parsed == ("06a01", "tag_category")
