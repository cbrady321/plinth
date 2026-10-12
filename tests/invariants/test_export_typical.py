"""Export flags on typical path — real export copies."""

from __future__ import annotations

from pathlib import Path

from plinth.config import PipelineConfig
from plinth.dataset.manifest_rows import normalize_manifest_rows
from plinth.registry import StageRegistry
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import (
    experiment_dir,
    find_final_stage_dir,
    prepare_work_dir,
    register_golden_stages,
    tier_config_path,
)


def test_export_flags_live_on_pipeline_config_not_exceptional_registry() -> None:
    config = PipelineConfig(
        name="export_demo",
        version="1",
        dag={
            "type": "sequential",
            "name": "root",
            "children": [{"type": "stage", "name": "allowlist_filter"}],
        },
        params={"allowlist_filter": {"allow": ["a.bin"]}},
        export_flags={"allowlist_filter": True},
    )
    assert config.export_flags.get("allowlist_filter") is True
    exceptional = StageRegistry.list_exceptional()
    assert "allowlist_filter" not in exceptional


def test_export_flags_create_export_tree_on_gt1(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt1")
    config = PipelineConfig.from_yaml(tier_config_path("gt1"))
    config.export_flags = {"allowlist_filter": True}
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt1", work)
    pipeline.run(input_source=str(work / "data" / "dataset"))

    exp = experiment_dir(work, "gt1")
    export_root = exp / "export"
    assert export_root.is_dir()
    export_dirs = [p for p in export_root.iterdir() if p.is_dir()]
    assert export_dirs
    assert any((p / "manifest.csv").exists() for p in export_dirs)


def test_export_flags_do_not_change_gt1_manifest(tmp_path: Path) -> None:
    work_plain = prepare_work_dir(tmp_path / "plain", "gt1")
    work_export = prepare_work_dir(tmp_path / "export", "gt1")

    register_golden_stages()
    plain_config = PipelineConfig.from_yaml(tier_config_path("gt1"))
    pipeline = Pipeline(plain_config, "golden_gt1", work_plain)
    pipeline.run(input_source=str(work_plain / "data" / "dataset"))
    plain_manifest = normalize_manifest_rows(
        find_final_stage_dir(experiment_dir(work_plain, "gt1")) / "manifest.csv"
    )

    export_config = PipelineConfig.from_yaml(tier_config_path("gt1"))
    export_config.export_flags = {"allowlist_filter": True}
    register_golden_stages()
    pipeline_export = Pipeline(export_config, "golden_gt1", work_export)
    pipeline_export.run(input_source=str(work_export / "data" / "dataset"))
    export_manifest = normalize_manifest_rows(
        find_final_stage_dir(experiment_dir(work_export, "gt1")) / "manifest.csv"
    )

    assert plain_manifest == export_manifest


def test_export_refreshed_on_stage_resume(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    config = PipelineConfig.from_yaml(tier_config_path("gt2"))
    config.export_flags = {"allowlist_filter": True}
    register_golden_stages()
    dataset = str(work / "data" / "dataset")

    pipeline = Pipeline(config, "golden_gt2", work)
    pipeline.run(input_source=dataset, end_at_stage="allowlist_filter")

    exp = experiment_dir(work, "gt2")
    export_before = list((exp / "export").iterdir())

    pipeline.run(input_source=dataset, start_from_stage="allowlist_filter")
    export_after = list((exp / "export").iterdir())
    assert export_after
    assert len(export_before) == len(export_after)


def test_unknown_export_flag_stage_is_ignored_at_runtime(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt1")
    config = PipelineConfig.from_yaml(tier_config_path("gt1"))
    config.export_flags = {"not_a_stage": True, "allowlist_filter": False}
    register_golden_stages()
    pipeline = Pipeline(config, "golden_gt1", work)
    pipeline.run(input_source=str(work / "data" / "dataset"))
    assert not (experiment_dir(work, "gt1") / "export").exists()
