"""parallel_error_policy continue yields incomplete lineage on full pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import prepare_work_dir


class _OkBranchStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            reads_files=False,
            modifies_files=False,
            write_columns={"ok": "bool"},
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(ok=True)


class _FailingBranchStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            reads_files=False,
            modifies_files=False,
            write_columns={"fail_marker": "str"},
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        raise RuntimeError("branch failed")


class _JoinStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"ok", "fail_marker"},
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(joined=True)


def test_continue_policy_pipeline_fails_on_downstream_join(tmp_path: Path, isolated_registry: None) -> None:
    StageRegistry.register("continue_ok")(_OkBranchStage)
    StageRegistry.register("continue_fail")(_FailingBranchStage)
    StageRegistry.register("continue_join")(_JoinStage)

    work = prepare_work_dir(tmp_path)
    dataset = work / "data" / "dataset"
    config = PipelineConfig(
        name="continue_lineage",
        version="1",
        input_source="dataset",
        parallel_error_policy="continue",
        dag={
            "type": "sequential",
            "name": "root",
            "children": [
                {
                    "type": "parallel",
                    "name": "split",
                    "children": [
                        {"type": "stage", "name": "continue_ok"},
                        {"type": "stage", "name": "continue_fail"},
                    ],
                },
                {"type": "stage", "name": "continue_join"},
            ],
        },
        params={"continue_ok": {}, "continue_fail": {}, "continue_join": {}},
    )
    pipeline = Pipeline(config, "continue_exp", work)

    with pytest.raises(ValueError, match="fail_marker"):
        pipeline.run(input_source=str(dataset))
