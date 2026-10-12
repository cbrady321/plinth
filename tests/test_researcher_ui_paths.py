"""The researcher UI serves files from inside a run directory and nowhere else."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plinth.researcher_ui.app import create_app
from plinth.researcher_ui.services.run_index import resolve_run_dir, resolve_stage_dir

STAGE = "01_stage"
MANIFEST = "entity_id,value\na,1\n"


def _stage(directory: Path, manifest: str = MANIFEST, marker: str = "run") -> None:
    directory.mkdir(parents=True)
    (directory / "manifest.csv").write_text(manifest)
    (directory / "metadata_ledger.yaml").write_text(f"# {marker}\nentries: []\n")
    (directory / "dataset_schema.yaml").write_text(f"# {marker}\nschema_format: 1\n")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Two runs whose names share a prefix, plus secrets next to and above the runs directory."""
    runs = tmp_path / "data" / "pipeline" / "runs"
    _stage(runs / "run" / STAGE)
    (runs / "run" / "notes.txt").write_text("inside the run")
    _stage(runs / "runX" / STAGE, manifest="entity_id,value\nsibling,9\n", marker="sibling")
    (runs / "runX" / "secret.txt").write_text("SIBLING")
    (runs.parent / "secret.txt").write_text("PARENT")
    _stage(runs.parent / STAGE, manifest="entity_id,value\nparent,7\n", marker="parent")
    (tmp_path / "secret.txt").write_text("PROJECT")
    return tmp_path


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project))


def test_files_inside_a_run_are_served(client: TestClient) -> None:
    response = client.get("/api/runs/run/artifacts/download", params={"path": "notes.txt"})
    assert response.status_code == 200
    assert response.text == "inside the run"


@pytest.mark.parametrize(
    ("run_id", "path"),
    [
        ("%2E%2E", "secret.txt"),  # run id that is the parent directory
        ("run", "../runX/secret.txt"),  # sibling whose name starts with the run's name
        ("run", "../../secret.txt"),
        ("run", "../../../secret.txt"),
        ("run", "/etc/hosts"),
        ("%2E", "../secret.txt"),
    ],
)
def test_download_refuses_paths_outside_the_run(client: TestClient, run_id: str, path: str) -> None:
    response = client.get(f"/api/runs/{run_id}/artifacts/download", params={"path": path})
    assert response.status_code == 404
    assert "SIBLING" not in response.text and "PARENT" not in response.text and "PROJECT" not in response.text


@pytest.mark.parametrize("endpoint", ["", "/artifacts", "/ledger", "/failures"])
def test_parent_run_id_is_not_a_run(client: TestClient, endpoint: str) -> None:
    response = client.get(f"/api/runs/%2E%2E{endpoint}")
    assert response.status_code == 404 or "not found" in response.text.lower()
    assert "secret.txt" not in response.text


@pytest.mark.parametrize("endpoint", ["manifest", "schema", "ledger/export"])
def test_stage_paths_cannot_leave_the_run(client: TestClient, endpoint: str) -> None:
    for stage_path in (f"../runX/{STAGE}", f"../../{STAGE}"):
        response = client.get(f"/api/runs/run/{endpoint}", params={"stage_path": stage_path})
        assert "sibling" not in response.text and "parent" not in response.text, (endpoint, stage_path)
        if endpoint == "ledger/export":
            assert response.status_code == 404, stage_path


def test_entity_diff_cannot_leave_the_run(client: TestClient) -> None:
    response = client.get(
        "/api/compare/entity-diff", params={"runs": "run,runX", "stage_path": f"../../{STAGE}"}
    )
    assert "parent" not in response.text
    assert "Missing manifest" in response.json()["error"]


def test_resolvers_reject_escapes(project: Path) -> None:
    runs = project / "data" / "pipeline" / "runs"
    assert resolve_run_dir(runs, "run") == (runs / "run").resolve()
    for bad in ("", ".", "..", "run/../runX", "../runs/run", "run\\x", "missing"):
        assert resolve_run_dir(runs, bad) is None, bad
    run = resolve_run_dir(runs, "run")
    assert resolve_stage_dir(run, STAGE) == (runs / "run" / STAGE).resolve()
    assert resolve_stage_dir(run, f"../runX/{STAGE}") is None
    assert resolve_stage_dir(None, STAGE) is None


def test_run_symlinked_out_of_the_runs_directory_is_refused(project: Path) -> None:
    runs = project / "data" / "pipeline" / "runs"
    outside = project / "elsewhere"
    _stage(outside / STAGE)
    (runs / "linked").symlink_to(outside, target_is_directory=True)
    assert resolve_run_dir(runs, "linked") is None


def test_allowed_hosts_rejects_foreign_host_header(project: Path) -> None:
    client = TestClient(create_app(project, allowed_hosts=["127.0.0.1", "localhost"]), base_url="http://localhost")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"host": "attacker.example"}).status_code == 400
