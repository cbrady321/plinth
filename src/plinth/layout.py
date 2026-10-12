"""Where a project keeps its data, relative to the project root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataLayout:
    """Project-relative data geography. Inject a custom instance to change it."""

    data_dir: str = "data"
    runs_dir: str = "data/pipeline/runs"
    default_input_dir: str = "data/pipeline/publish/dataset"

    def data_root(self, project_root: Path) -> Path:
        return Path(project_root) / self.data_dir

    def run_dir(self, project_root: Path, experiment_name: str) -> Path:
        return Path(project_root) / self.runs_dir / experiment_name

    def input_dir(self, project_root: Path) -> Path:
        return Path(project_root) / self.default_input_dir

    def runs_root(self, project_root: Path) -> Path:
        return Path(project_root) / self.runs_dir
