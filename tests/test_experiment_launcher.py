from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from plinth.config import PipelineConfig
from plinth.experiment_launcher import ExperimentLauncher
from plinth.layout import DataLayout


def _empty_config(name: str) -> PipelineConfig:
    return PipelineConfig(
        name=name,
        version="1",
        dag={"type": "sequential", "name": "root", "children": []},
        params={},
    )


class _RecordingPipeline:
    """Stands in for ``Pipeline``: records the layout it was built with and creates its run dir."""

    built: list["_RecordingPipeline"] = []

    def __init__(self, config: PipelineConfig, experiment_name: str, project_root: Path, layout=None) -> None:
        self.layout = layout
        self.experiment_dir = layout.run_dir(project_root, experiment_name)
        _RecordingPipeline.built.append(self)

    def run(self, **kwargs: object) -> Path:
        self.experiment_dir.mkdir(parents=True)
        return self.experiment_dir


@pytest.fixture
def launcher_factory(monkeypatch: pytest.MonkeyPatch):
    _RecordingPipeline.built.clear()
    monkeypatch.setattr("plinth.experiment_launcher.Pipeline", _RecordingPipeline)

    def make(root: Path, **kwargs: object) -> ExperimentLauncher:
        launcher = ExperimentLauncher(root, **kwargs)
        monkeypatch.setattr(launcher, "validate", lambda _config: SimpleNamespace(ok=True, errors=[]))
        return launcher

    return make


def test_run_writes_under_default_layout_and_saves_config(tmp_path: Path, launcher_factory) -> None:
    result = launcher_factory(tmp_path).run(_empty_config("demo"), "first")

    assert result.output_dir == DataLayout().run_dir(tmp_path, "first")
    assert (result.output_dir / "pipeline_config.yaml").is_file()


def test_run_uses_injected_layout(tmp_path: Path, launcher_factory) -> None:
    layout = DataLayout(runs_dir="scratch/experiments")
    result = launcher_factory(tmp_path, layout=layout).run(_empty_config("demo"), "first")

    assert _RecordingPipeline.built[-1].layout is layout
    assert result.output_dir == tmp_path / "scratch/experiments/first"


def test_invalid_config_is_rejected_before_any_pipeline_is_built(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("plinth.experiment_launcher.Pipeline", _RecordingPipeline)
    _RecordingPipeline.built.clear()
    launcher = ExperimentLauncher(tmp_path)
    monkeypatch.setattr(launcher, "validate", lambda _config: SimpleNamespace(ok=False, errors=["dag: broken"]))

    with pytest.raises(ValueError, match="dag: broken"):
        launcher.run(_empty_config("demo"), "first")
    assert _RecordingPipeline.built == []
