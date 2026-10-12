"""FastAPI application for the Pipeline Researcher UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from plinth.layout import DataLayout
from plinth.researcher_ui.models import ExportRequest, RunListResponse
from plinth.researcher_ui.services.artifacts import load_artifact_tree, resolve_artifact_path
from plinth.researcher_ui.services.compare import (
    compare_configs,
    compare_entity_diff,
    compare_ledgers,
    compare_manifest_summaries,
    export_comparison_report,
)
from plinth.researcher_ui.services.failures import load_failure_report
from plinth.researcher_ui.services.ledger import export_raw_ledger, load_ledger_timeline
from plinth.researcher_ui.services.manifest import load_manifest_page, load_schema_summary
from plinth.researcher_ui.services.run_index import get_run, list_runs


def create_app(
    project_root: Path | None = None,
    layout: DataLayout | None = None,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    """Build the UI app. ``allowed_hosts`` restricts the HTTP ``Host`` header (``None``: any host)."""
    project = Path(project_root or Path.cwd()).resolve()
    root = (layout or DataLayout()).runs_root(project)
    app = FastAPI(title="Plinth Researcher UI", version="0.1.0")
    if allowed_hosts is not None:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    static_dir = Path(__file__).parent / "static"

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "project_root": str(project), "runs_dir": str(root)}

    @app.get("/api/runs", response_model=RunListResponse)
    def api_list_runs(
        status: str | None = None,
        sort: str = Query(default="recency", pattern="^(recency|status|duration)$"),
        from_date: str | None = Query(default=None, description="ISO timestamp lower bound"),
        to_date: str | None = Query(default=None, description="ISO timestamp upper bound"),
    ) -> RunListResponse:
        try:
            runs = list_runs(root, status_filter=status, sort=sort, from_date=from_date, to_date=to_date)
            return RunListResponse(runs=runs)
        except Exception as exc:
            return RunListResponse(runs=[], error=str(exc))

    @app.get("/api/runs/{run_id}")
    def api_get_run(run_id: str):
        detail = get_run(root, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        return detail

    @app.get("/api/runs/{run_id}/manifest")
    def api_manifest(
        run_id: str,
        stage_path: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=500),
        entity_id: str | None = None,
    ):
        return load_manifest_page(root, run_id, stage_path, page=page, page_size=page_size, entity_id=entity_id)

    @app.get("/api/runs/{run_id}/schema")
    def api_schema(run_id: str, stage_path: str):
        return load_schema_summary(root, run_id, stage_path)

    @app.get("/api/runs/{run_id}/ledger")
    def api_ledger(run_id: str):
        return load_ledger_timeline(root, run_id)

    @app.get("/api/runs/{run_id}/ledger/export")
    def api_ledger_export(run_id: str, stage_path: str):
        path = export_raw_ledger(root, run_id, stage_path)
        if path is None:
            raise HTTPException(status_code=404, detail="Ledger file not found")
        return FileResponse(path, filename=path.name, media_type="application/x-yaml")

    @app.get("/api/runs/{run_id}/failures")
    def api_failures(run_id: str):
        return load_failure_report(root, run_id)

    @app.get("/api/runs/{run_id}/artifacts")
    def api_artifacts(run_id: str):
        return load_artifact_tree(root, run_id)

    @app.get("/api/runs/{run_id}/artifacts/download")
    def api_artifact_download(run_id: str, path: str):
        file_path = resolve_artifact_path(root, run_id, path)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return FileResponse(file_path, filename=file_path.name)

    @app.get("/api/compare/config")
    def api_compare_config(runs: str = Query(..., description="Comma-separated run IDs")):
        run_ids = [part.strip() for part in runs.split(",") if part.strip()]
        return compare_configs(root, run_ids)

    @app.get("/api/compare/manifest-summary")
    def api_compare_manifest_summary(runs: str):
        run_ids = [part.strip() for part in runs.split(",") if part.strip()]
        return compare_manifest_summaries(root, run_ids)

    @app.get("/api/compare/entity-diff")
    def api_compare_entity_diff(
        runs: str,
        stage_path: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
    ):
        run_ids = [part.strip() for part in runs.split(",") if part.strip()]
        return compare_entity_diff(root, run_ids, stage_path, page=page, page_size=page_size)

    @app.get("/api/compare/ledger")
    def api_compare_ledger(runs: str):
        run_ids = [part.strip() for part in runs.split(",") if part.strip()]
        return compare_ledgers(root, run_ids)

    @app.post("/api/compare/export")
    def api_compare_export(request: ExportRequest):
        body = export_comparison_report(root, request)
        media_type = "text/markdown" if request.format == "markdown" else "application/json"
        filename = f"comparison.{ 'md' if request.format == 'markdown' else 'json' }"
        return PlainTextResponse(
            content=body,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if static_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

        @app.get("/")
        def index():
            return FileResponse(static_dir / "index.html")

    return app
