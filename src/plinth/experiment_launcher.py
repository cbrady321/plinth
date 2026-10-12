"""Shared experiment entry plumbing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from plinth.config import PipelineConfig
from plinth.layout import DataLayout
from plinth.runtime.pipeline import Pipeline
from plinth.validation import ValidationResult, validate_pipeline_config


@dataclass
class ExperimentLaunchResult:
    output_dir: Path
    experiment_name: str


class ExperimentLauncher:
    def __init__(
        self,
        project_root: Path,
        *,
        layout: Optional[DataLayout] = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.layout = layout or DataLayout()

    def validate(self, config: PipelineConfig) -> ValidationResult:
        return validate_pipeline_config(config)

    def run(
        self,
        config: PipelineConfig,
        experiment_name: str,
        *,
        input_source: Optional[str] = None,
        start_from_stage: Optional[str] = None,
    ) -> ExperimentLaunchResult:
        result = self.validate(config)
        if not result.ok:
            raise ValueError("Invalid pipeline config:\n" + "\n".join(result.errors))

        pipeline = Pipeline(config, experiment_name, self.project_root, layout=self.layout)
        output_dir = pipeline.run(
            input_source=input_source,
            start_from_stage=start_from_stage,
        )
        config.to_yaml(pipeline.experiment_dir / "pipeline_config.yaml")
        return ExperimentLaunchResult(output_dir=Path(output_dir), experiment_name=experiment_name)
