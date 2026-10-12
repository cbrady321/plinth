"""Integration tests for flow-control runtime wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from plinth.blocks import ParallelBlock, StageNode
from plinth.flow import FlowArmingConfig, ParallelFanInPolicy, RunIdentity, WaitMode, port_id_for_parallel_child
from plinth.flow.overlay import DefaultArmingOverlay
from plinth.flow.runtime import (
    FlowRunContext,
    attach_flow_run_context,
    build_flow_run_context,
)


class MockStage:
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
        from plinth.intent import StageIntent

        return StageIntent()


@patch("plinth.blocks.StageRegistry")
def test_parallel_block_skips_disarmed_branch(mock_registry, tmp_path: Path) -> None:
    mock_registry.get_stage.return_value = MockStage

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
    flow_context = FlowRunContext(
        run_identity=run_identity,
        overlay=DefaultArmingOverlay(run_identity=run_identity, config=flow_config),
    )
    attach_flow_run_context(parallel, flow_context)

    output_dir = tmp_path / "output"
    result = parallel.execute([input_dir], output_dir, "a", parent_location_code="")

    assert (output_dir / "a_fan").exists()
    assert (output_dir / "a_branch_a").exists()
    assert (output_dir / "b_branch_b").exists()
    assert not (output_dir / "c_branch_c").exists()
    assert result.block_type == "parallel"
    assert len(result.output_dirs) == 1


def test_build_flow_run_context_returns_none_when_inactive() -> None:
    from plinth.config import PipelineConfig

    config = PipelineConfig(name="p", version="1.0", dag={"type": "stage", "name": "s"})
    dag = config.build_dag()
    assert build_flow_run_context(config, "exp", dag) is None


def test_build_flow_run_context_when_flow_arming_active() -> None:
    from plinth.config import PipelineConfig

    config = PipelineConfig(
        name="p",
        version="1.0",
        dag={
            "type": "parallel",
            "name": "fan",
            "children": [
                {"type": "stage", "name": "branch_a"},
                {"type": "stage", "name": "branch_b"},
            ],
        },
        flow_arming=FlowArmingConfig(
            parallel_policies={
                "fan": ParallelFanInPolicy(
                    wait_mode=WaitMode.WAIT_ARMED,
                    armed_children=frozenset({"branch_a"}),
                )
            }
        ),
    )
    dag = config.build_dag()
    context = build_flow_run_context(config, "exp", dag)
    assert context is not None
    assert "fan/branch_a" in context.run_identity.arming.armed_port_ids
