"""Empty registry smoke test."""

from __future__ import annotations

import importlib
import sys

import pytest

from plinth.registry import StageRegistry


def test_pipeline_constructs_with_empty_registry(isolated_registry: None) -> None:
    sys.modules.pop("plinth.runtime.pipeline", None)
    pipeline_module = importlib.import_module("plinth.runtime.pipeline")
    from plinth.config import PipelineConfig

    config = PipelineConfig(
        name="empty",
        version="1",
        dag={"type": "sequential", "name": "root", "children": []},
        params={},
    )
    pipeline = pipeline_module.Pipeline(config, "smoke", "/tmp")
    assert pipeline.experiment_name == "smoke"


def test_stage_lookup_fails_without_registration(isolated_registry: None) -> None:
    with pytest.raises(KeyError, match="not found in registry"):
        StageRegistry.get_stage("allowlist_filter")
