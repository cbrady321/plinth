"""Tests for researcher UI services and API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plinth.researcher_ui.app import create_app
from plinth.researcher_ui.models import ExportRequest
from plinth.researcher_ui.services.artifacts import load_artifact_tree
from plinth.researcher_ui.services.compare import (
    compare_entity_diff,
    compare_manifest_summaries,
    export_comparison_report,
)
from plinth.researcher_ui.services.config_diff import diff_configs
from plinth.researcher_ui.services.ledger import load_ledger_timeline
from plinth.researcher_ui.services.manifest import load_manifest_page, load_schema_summary
from plinth.researcher_ui.services.run_index import get_run, list_runs


@pytest.fixture
def demo_project(tmp_path: Path) -> Path:
    from plinth.config import PipelineConfig
    from plinth.experiment_launcher import ExperimentLauncher
    from plinth.registry import StageRegistry
    from tests.golden.golden_stages import register_all_golden_stages

    fixture_root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_pipeline"
    dataset_dst = tmp_path / "data" / "dataset"
    dataset_dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copytree(fixture_root / "input" / "dataset", dataset_dst)
    StageRegistry.clear()
    register_all_golden_stages()
    config = PipelineConfig.from_yaml(fixture_root / "config.yaml")
    launcher = ExperimentLauncher(tmp_path)
    launcher.run(config, "ui_test_run", input_source=str(dataset_dst))

    config_b = PipelineConfig.from_yaml(fixture_root / "config.yaml")
    config_b.params.setdefault("allowlist_filter", {})["allow"] = ["a.bin", "b.bin"]
    launcher.run(config_b, "ui_test_run_b", input_source=str(dataset_dst))
    return tmp_path


@pytest.fixture
def runs_dir(demo_project: Path) -> Path:
    return demo_project / "data" / "pipeline" / "runs"


def test_launcher_writes_config_snapshot(demo_project: Path) -> None:
    snapshot = demo_project / "data" / "pipeline" / "runs" / "ui_test_run" / "pipeline_config.yaml"
    assert snapshot.exists()
    import yaml

    data = yaml.safe_load(snapshot.read_text(encoding="utf-8"))
    assert data["name"] == "golden_minimal"


def test_large_manifest_pagination(demo_project: Path, runs_dir: Path) -> None:
    import pandas as pd

    detail = get_run(runs_dir, "ui_test_run")
    stage_path = detail.stages[-1].stage_path
    manifest_path = demo_project / "data" / "pipeline" / "runs" / "ui_test_run" / stage_path / "manifest.csv"
    base = pd.read_csv(manifest_path)
    large = pd.concat([base] * 2000, ignore_index=True)
    large["row_number"] = range(len(large))
    large.to_csv(manifest_path, index=False)

    page1 = load_manifest_page(runs_dir, "ui_test_run", stage_path, page=1, page_size=50)
    assert page1.total_rows == len(large)
    assert page1.total_pages > 1
    assert len(page1.rows) == 50

    page2 = load_manifest_page(runs_dir, "ui_test_run", stage_path, page=2, page_size=50)
    assert len(page2.rows) == 50
    assert [row["row_number"] for row in page1.rows] == list(range(50))
    assert [row["row_number"] for row in page2.rows] == list(range(50, 100))
    # Empty cells come back as None (valid JSON), never NaN.
    assert all(value is None or value == value for row in page2.rows for value in row.values())


def test_list_and_get_run(runs_dir: Path) -> None:
    runs = list_runs(runs_dir)
    assert len(runs) == 2
    assert runs[0].run_id in {"ui_test_run", "ui_test_run_b"}
    assert runs[0].status == "success"

    detail = get_run(runs_dir, "ui_test_run")
    assert detail is not None
    assert detail.pipeline_name == "golden_minimal"
    assert len(detail.stages) >= 2
    assert all(stage.has_manifest for stage in detail.stages)


def test_manifest_and_schema(runs_dir: Path) -> None:
    detail = get_run(runs_dir, "ui_test_run")
    assert detail is not None
    stage_path = detail.stages[-1].stage_path

    page = load_manifest_page(runs_dir, "ui_test_run", stage_path, page=1, page_size=10)
    assert page.error is None
    assert page.total_rows >= 1
    assert page.manifest_path is not None
    assert page.manifest_size_bytes is not None
    assert page.total_pages >= 1

    schema = load_schema_summary(runs_dir, "ui_test_run", stage_path)
    assert schema.error is None
    assert schema.identity.get("entity_key") == "entity_id"
    assert schema.media == {"path_column": "file_path", "subdir": "files", "name_column": ""}


def test_schema_summary_reports_schema_without_format_as_error(demo_project: Path, runs_dir: Path) -> None:
    import yaml

    detail = get_run(runs_dir, "ui_test_run")
    assert detail is not None
    stage_path = detail.stages[-1].stage_path
    schema_file = demo_project / "data" / "pipeline" / "runs" / "ui_test_run" / stage_path / "dataset_schema.yaml"
    data = yaml.safe_load(schema_file.read_text())
    data.pop("schema_format")
    schema_file.write_text(yaml.dump(data))

    schema = load_schema_summary(runs_dir, "ui_test_run", stage_path)
    assert schema.error is not None
    assert "schema_format" in schema.error


def test_ledger_timeline(runs_dir: Path) -> None:
    timeline = load_ledger_timeline(runs_dir, "ui_test_run")
    assert timeline.error is None or "No completed stages" in (timeline.error or "")
    assert timeline.entries
    executed = [e for e in timeline.entries if e.status == "executed"]
    assert executed
    assert executed[0].params_hash
    assert timeline.integrity_ok


def test_config_structural_diff() -> None:
    left = {"params": {"a": 1}, "dag": {"type": "stage", "name": "x"}}
    right = {"params": {"a": 2}, "dag": {"type": "stage", "name": "x"}}
    diffs = diff_configs([left, right], ["run_a", "run_b"])
    paths = {d["path"] for d in diffs}
    assert "$.params.a" in paths


def test_compare_manifest_mismatch(runs_dir: Path) -> None:
    summary = compare_manifest_summaries(runs_dir, ["ui_test_run", "ui_test_run_b"])
    assert summary.rows
    assert any(row.mismatch for row in summary.rows)


def test_compare_entity_diff_pagination(runs_dir: Path) -> None:
    detail = get_run(runs_dir, "ui_test_run")
    stage_path = detail.stages[-1].stage_path
    page = compare_entity_diff(runs_dir, ["ui_test_run", "ui_test_run_b"], stage_path, page=1, page_size=5)
    assert page.error is None
    assert page.total_pages >= 1


def test_export_report_includes_metadata(runs_dir: Path) -> None:
    body = export_comparison_report(
        runs_dir,
        ExportRequest(run_ids=["ui_test_run", "ui_test_run_b"], sections=["config", "ledger"], format="markdown"),
    )
    assert "ui_test_run" in body
    assert "## Run metadata" in body


def test_failed_run_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "data" / "pipeline" / "runs" / "failed_run"
    run_dir.mkdir(parents=True)
    (run_dir / ".run_error.json").write_text(
        json.dumps(
            {
                "stage_path": "03_broken_stage",
                "message": "Stage logic failure",
                "kind": "stage_logic",
                "row_failures": [{"entity_id": "e1", "stage_path": "03_broken_stage", "error_message": "bad row"}],
                "cancelled_branches": ["branch_b"],
            }
        ),
        encoding="utf-8",
    )

    from plinth.researcher_ui.services.failures import load_failure_report

    report = load_failure_report(tmp_path / "data" / "pipeline" / "runs", "failed_run")
    assert report.status == "failed"
    assert report.error_kind == "stage_logic"
    assert report.row_failures[0].entity_id == "e1"
    assert report.cancelled_branches == ["branch_b"]


def test_manifest_entity_filter(runs_dir: Path) -> None:
    detail = get_run(runs_dir, "ui_test_run")
    stage_path = detail.stages[-1].stage_path
    full = load_manifest_page(runs_dir, "ui_test_run", stage_path, page=1, page_size=50)
    assert full.total_rows >= 1
    entity_id = str(full.rows[0].get("entity_id") or "")
    assert entity_id
    filtered = load_manifest_page(
        runs_dir, "ui_test_run", stage_path, page=1, page_size=50, entity_id=entity_id
    )
    assert filtered.entity_filter == entity_id
    assert filtered.total_rows >= 1
    assert all(str(row.get("entity_id") or "") == entity_id for row in filtered.rows)


def test_artifact_export_flags(demo_project: Path, runs_dir: Path) -> None:
    import yaml

    run_dir = demo_project / "data" / "pipeline" / "runs" / "ui_test_run"
    config_path = run_dir / "pipeline_config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    detail = get_run(runs_dir, "ui_test_run")
    stage_name = detail.stages[-1].stage_name
    config["export_flags"] = {stage_name: True}
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    tree = load_artifact_tree(runs_dir, "ui_test_run")
    stage_node = next(
        child for child in (tree.root.children or []) if child.name == detail.stages[-1].stage_path
    )
    assert stage_node.export_warning == "export enabled but export tree missing"

    export_dir = run_dir / "export" / detail.stages[-1].stage_path
    export_dir.mkdir(parents=True)
    (export_dir / "marker.txt").write_text("ok", encoding="utf-8")
    tree_with_export = load_artifact_tree(runs_dir, "ui_test_run")
    stage_node = next(
        child for child in (tree_with_export.root.children or []) if child.name == detail.stages[-1].stage_path
    )
    assert stage_node.export_label == "export enabled"
    assert stage_node.export_warning is None


def test_api_endpoints(demo_project: Path) -> None:
    client = TestClient(create_app(demo_project))
    health = client.get("/api/health")
    assert health.status_code == 200

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert len(runs.json()["runs"]) == 2

    detail = client.get("/api/runs/ui_test_run")
    assert detail.status_code == 200
    stage_path = detail.json()["stages"][-1]["stage_path"]

    manifest = client.get(f"/api/runs/ui_test_run/manifest?stage_path={stage_path}")
    assert manifest.status_code == 200
    assert manifest.json()["total_rows"] >= 1

    ledger = client.get("/api/runs/ui_test_run/ledger")
    assert ledger.status_code == 200

    artifacts = client.get("/api/runs/ui_test_run/artifacts")
    assert artifacts.status_code == 200
    artifact_root = artifacts.json()["root"]
    assert artifact_root["kind"] == "directory"
    assert any("golden" in child["name"] or child["name"].startswith("01_") for child in artifact_root["children"])

    compare = client.get("/api/compare/config?runs=ui_test_run,ui_test_run_b")
    assert compare.status_code == 200
    assert compare.json()["structural_diffs"]

    export = client.post(
        "/api/compare/export",
        json={"run_ids": ["ui_test_run", "ui_test_run_b"], "sections": ["ledger"], "format": "json"},
    )
    assert export.status_code == 200
    assert "ledger" in export.text

    index = client.get("/")
    assert index.status_code == 200


def test_api_uses_injected_layout(tmp_path: Path) -> None:
    from plinth.layout import DataLayout

    (tmp_path / "elsewhere" / "runs" / "custom_run").mkdir(parents=True)
    client = TestClient(create_app(tmp_path, layout=DataLayout(runs_dir="elsewhere/runs")))
    assert client.get("/api/health").json()["runs_dir"] == str(tmp_path / "elsewhere" / "runs")
    assert [run["run_id"] for run in client.get("/api/runs").json()["runs"]] == ["custom_run"]
