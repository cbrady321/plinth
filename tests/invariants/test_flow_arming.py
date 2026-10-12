"""Flow-control arming overlay invariants."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from plinth.blocks import ParallelBlock, StageNode
from plinth.config import PipelineConfig
from plinth.context import FileSystemStageContext, StageContext
from plinth.dataset.structures import MetadataLedger
from plinth.flow import FlowArmingConfig, ParallelFanInPolicy, WaitMode, port_id_for_parallel_child
from plinth.flow.overlay import DefaultArmingOverlay
from plinth.flow.resume import validate_arming_on_resume
from plinth.flow.runtime import FlowRunContext, attach_flow_run_context
from plinth.intent import StageIntent
from plinth.registry import ExceptionalObligations, StageRegistry
from plinth.runtime.exceptional_executor import ExceptionalStageExecutor
from plinth.runtime.ledger_writer import LedgerWriter
from tests.golden.golden_stages import register_all_golden_stages


class MockTypicalStage:
    def __init__(self, stage_name: str, config: dict):
        self.stage_name = stage_name
        self.config = config
        self._files_processed = 1

    def prepare_context(self, context):
        return None

    def finalize_output(self, context, output_dir):
        return output_dir

    def _process_all_files(self, input_dir, output_dir, manifest):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "output.txt").write_text(self.stage_name)

    def get_intent(self):
        return StageIntent()


class MockExceptionalStage:
    stage_name = "mock_exceptional"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def get_intent(self) -> StageIntent:
        return StageIntent()

    def execute(self, context: StageContext) -> Path:
        output_dir = context.get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        ledger = context.get_ledger()
        input_dir = context.get_input_dir()
        from plinth.runtime.hashing import compute_directory_hash, compute_params_hash

        LedgerWriter().append_entry(
            ledger,
            stage_name=self.stage_name,
            function_name=self.__class__.__name__,
            input_directory=str(input_dir),
            output_directory=str(output_dir),
            input_hash=compute_directory_hash(input_dir),
            output_hash=compute_directory_hash(output_dir),
            params_hash=compute_params_hash(self.config),
            params=dict(self.config),
            files_processed=0,
            duration_seconds=0.01,
        )
        LedgerWriter().write(ledger, output_dir)
        return output_dir



def _parallel_dag() -> dict:
    return {
        "type": "parallel",
        "name": "fan",
        "children": [
            {"type": "stage", "name": "golden_branch_a"},
            {"type": "stage", "name": "golden_branch_b"},
            {"type": "stage", "name": "golden_noop"},
        ],
    }


def _parallel_params() -> dict:
    return {"golden_branch_a": {}, "golden_branch_b": {}, "golden_noop": {}}


def test_validate_rejects_unknown_disarmed_port() -> None:
    register_all_golden_stages()
    config = PipelineConfig(
        name="flow",
        version="1",
        dag=_parallel_dag(),
        params=_parallel_params(),
        flow_arming=FlowArmingConfig(
            disarmed_ports=frozenset({"fan/missing_branch"}),
        ),
    )
    result = config.validate()
    assert not result.ok
    assert any("unknown port" in err for err in result.errors)


def test_validate_rejects_unknown_parallel_policy_block() -> None:
    register_all_golden_stages()
    config = PipelineConfig(
        name="flow",
        version="1",
        dag=_parallel_dag(),
        params=_parallel_params(),
        flow_arming=FlowArmingConfig(
            parallel_policies={
                "missing_fan": ParallelFanInPolicy(
                    wait_mode=WaitMode.WAIT_ARMED,
                    armed_children=frozenset({"golden_branch_a"}),
                )
            }
        ),
    )
    result = config.validate()
    assert not result.ok
    assert any("unknown parallel block" in err for err in result.errors)


def test_validate_rejects_unknown_armed_child() -> None:
    register_all_golden_stages()
    config = PipelineConfig(
        name="flow",
        version="1",
        dag=_parallel_dag(),
        params=_parallel_params(),
        flow_arming=FlowArmingConfig(
            parallel_policies={
                "fan": ParallelFanInPolicy(
                    wait_mode=WaitMode.WAIT_ARMED,
                    armed_children=frozenset({"golden_branch_a", "branch_z"}),
                )
            }
        ),
    )
    result = config.validate()
    assert not result.ok
    assert any("unknown child name" in err for err in result.errors)


@patch("plinth.blocks.StageRegistry")
def test_disarmed_parallel_branch_not_executed(mock_registry, tmp_path: Path) -> None:
    mock_registry.get_stage.return_value = MockTypicalStage

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "test.bin").write_text("data")

    config: dict = {"params": {"branch_a": {}, "branch_b": {}, "branch_c": {}}}
    children = [
        StageNode("branch_a", config),
        StageNode("branch_b", config),
        StageNode("branch_c", config),
    ]
    parallel = ParallelBlock("fan", config, children)

    from plinth.flow.identity import RunIdentity

    flow_config = FlowArmingConfig(
        parallel_policies={
            "fan": ParallelFanInPolicy(
                wait_mode=WaitMode.WAIT_ARMED,
                armed_children=frozenset({"branch_a", "branch_b"}),
            )
        }
    )
    run_identity = RunIdentity.from_arming(
        experiment_name="exp",
        pipeline_name="pipe",
        pipeline_version="1.0",
        armed_port_ids=[
            port_id_for_parallel_child("fan", "branch_a"),
            port_id_for_parallel_child("fan", "branch_b"),
        ],
    )
    attach_flow_run_context(
        parallel,
        FlowRunContext(
            run_identity=run_identity,
            overlay=DefaultArmingOverlay(run_identity=run_identity, config=flow_config),
        ),
    )

    output_dir = tmp_path / "output"
    parallel.execute([input_dir], output_dir, "a", parent_location_code="")

    assert (output_dir / "a_branch_a").exists()
    assert (output_dir / "b_branch_b").exists()
    assert not (output_dir / "c_branch_c").exists()


def test_exceptional_executor_stamps_arming_hash(tmp_path: Path) -> None:
    saved = StageRegistry._stages.get("mock_exceptional")
    saved_meta = StageRegistry._exceptional_metadata.get("mock_exceptional")
    StageRegistry.register(
        "mock_exceptional",
        mode="exceptional",
        obligations=ExceptionalObligations(
            records_ledger=True,
            hands_off_manifest=False,
            uses_resolver_address=False,
        ),
    )(MockExceptionalStage)
    try:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        context = FileSystemStageContext(input_dir, output_dir)

        ExceptionalStageExecutor().run(MockExceptionalStage(), context, arming_hash="abc123")
        ledger = MetadataLedger.from_directory(output_dir)
        assert ledger.entries[-1].arming_hash == "abc123"
    finally:
        if saved is None:
            StageRegistry._stages.pop("mock_exceptional", None)
            StageRegistry._modes.pop("mock_exceptional", None)
            StageRegistry._exceptional_metadata.pop("mock_exceptional", None)
        else:
            StageRegistry._stages["mock_exceptional"] = saved
            if saved_meta is not None:
                StageRegistry._exceptional_metadata["mock_exceptional"] = saved_meta


def test_resume_rejects_arming_drift(tmp_path: Path) -> None:
    from plinth.blocks import SequentialBlock
    from plinth.flow.identity import RunIdentity

    stage_a = StageNode("stage_a", {"params": {}})
    stage_b = StageNode("stage_b", {"params": {}})
    dag = SequentialBlock("root", {}, [stage_a, stage_b])

    experiment_dir = tmp_path / "exp"
    stage_a_dir = experiment_dir / "01_stage_a"
    stage_a_dir.mkdir(parents=True)
    ledger = MetadataLedger()
    LedgerWriter().append_entry(
        ledger,
        stage_name="stage_a",
        function_name="Mock",
        input_directory=str(tmp_path / "in"),
        output_directory=str(stage_a_dir),
        input_hash="in",
        output_hash="out",
        params_hash="params",
        params={},
        files_processed=1,
        duration_seconds=0.01,
        arming_hash="old_hash",
    )
    LedgerWriter().write(ledger, stage_a_dir)

    run_identity = RunIdentity.from_arming(
        experiment_name="exp",
        pipeline_name="pipe",
        pipeline_version="1.0",
        armed_port_ids=["fan/branch_a"],
    )

    with pytest.raises(ValueError, match="arming changed"):
        validate_arming_on_resume(experiment_dir, dag, "stage_b", run_identity)
