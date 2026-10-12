"""Seed demo runs for the researcher UI from the golden pipeline fixtures.

Usage: python scripts/seed_researcher_ui_demo.py [--project-root DIR]
Lives outside the installed package because it depends on the test fixtures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _seed_demo_runs(project_root: Path) -> None:
    import shutil

    from plinth.config import PipelineConfig
    from plinth.experiment_launcher import ExperimentLauncher

    fixture_config = (
        Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_pipeline" / "config.yaml"
    )
    dataset_src = (
        Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_pipeline" / "input" / "dataset"
    )
    if not fixture_config.exists():
        raise SystemExit(f"Demo fixture config not found: {fixture_config}")

    work = project_root
    dataset_dst = work / "data" / "dataset"
    dataset_dst.parent.mkdir(parents=True, exist_ok=True)
    if dataset_dst.exists():
        shutil.rmtree(dataset_dst)
    shutil.copytree(dataset_src, dataset_dst)

    from plinth.registry import StageRegistry
    from tests.golden.golden_stages import register_all_golden_stages

    StageRegistry.clear()
    register_all_golden_stages()

    config = PipelineConfig.from_yaml(fixture_config)
    launcher = ExperimentLauncher(work)
    launcher.run(config, "demo_run_001", input_source=str(dataset_dst))
    config.to_yaml(work / "data" / "pipeline" / "runs" / "demo_run_001" / "pipeline_config.yaml")

    # Second variant with a tweaked param for comparison demos.
    config_b = PipelineConfig.from_yaml(fixture_config)
    config_b.params.setdefault("allowlist_filter", {})["allow"] = ["a.bin", "b.bin"]
    launcher.run(config_b, "demo_run_002", input_source=str(dataset_dst))
    config_b.to_yaml(work / "data" / "pipeline" / "runs" / "demo_run_002" / "pipeline_config.yaml")

    print(f"Seeded demo runs under {work / 'data' / 'pipeline' / 'runs'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    _seed_demo_runs(parser.parse_args().project_root.resolve())
