"""Tests for flow-control interface contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.flow import (
    ArmedInputMissingError,
    ArmingContractError,
    ArmingSnapshot,
    DefaultArmingOverlay,
    EmptyArmingMaskError,
    FlowArmingConfig,
    ParallelFanInPolicy,
    RunIdentity,
    WaitAllMaskMismatchError,
    WaitMode,
    compute_arming_hash,
    port_id_for_parallel_child,
)
from plinth.flow.config import FlowArmingConfig as FlowArmingConfigType
from plinth.flow.policies import DefaultCombineWaitPolicy
from plinth.flow.types import CombineMode


def test_arming_snapshot_sorts_and_hashes_deterministically() -> None:
    first = ArmingSnapshot.from_port_ids(["source_c", "source_a", "source_b"])
    second = ArmingSnapshot.from_port_ids(["source_b", "source_a", "source_c"])
    assert first.armed_port_ids == ("source_a", "source_b", "source_c")
    assert compute_arming_hash(first) == compute_arming_hash(second)


def test_arming_snapshot_rejects_duplicate_port_ids() -> None:
    with pytest.raises(ArmingContractError):
        ArmingSnapshot(armed_port_ids=("a", "a"))


def test_run_identity_resume_key_includes_arming_hash() -> None:
    identity_a = RunIdentity.from_arming(
        experiment_name="exp",
        pipeline_name="pipe",
        pipeline_version="1.0",
        armed_port_ids=["a", "b"],
    )
    identity_b = RunIdentity.from_arming(
        experiment_name="exp",
        pipeline_name="pipe",
        pipeline_version="1.0",
        armed_port_ids=["a"],
    )
    assert identity_a.resume_key() != identity_b.resume_key()


def test_flow_arming_config_from_mapping() -> None:
    config = FlowArmingConfig.from_mapping(
        {
            "disarmed_ports": ["fan/source_c"],
            "parallel_policies": {
                "fan": {
                    "wait_mode": "wait_armed",
                    "combine_mode": "aggregate",
                    "armed_children": ["source_a", "source_b"],
                }
            },
        }
    )
    assert "fan/source_c" in config.disarmed_ports
    policy = config.parallel_policy("fan")
    assert policy.wait_mode is WaitMode.WAIT_ARMED
    assert policy.combine_mode is CombineMode.AGGREGATE
    assert policy.armed_children == frozenset({"source_a", "source_b"})


def test_wait_all_rejects_partial_armed_children() -> None:
    with pytest.raises(WaitAllMaskMismatchError):
        ParallelFanInPolicy(
            wait_mode=WaitMode.WAIT_ALL,
            armed_children=frozenset({"only_one"}),
        )


def test_default_combine_wait_policy_wait_armed_skips_disarmed() -> None:
    policy = DefaultCombineWaitPolicy(
        ParallelFanInPolicy(wait_mode=WaitMode.WAIT_ARMED, armed_children=frozenset({"a", "b"}))
    )
    upstream = {
        port_id_for_parallel_child("fan", "a"): Path("/tmp/a"),
        port_id_for_parallel_child("fan", "b"): Path("/tmp/b"),
        port_id_for_parallel_child("fan", "c"): None,
    }
    armed = {
        port_id_for_parallel_child("fan", "a"): True,
        port_id_for_parallel_child("fan", "b"): True,
        port_id_for_parallel_child("fan", "c"): False,
    }
    resolved = policy.resolve(upstream=upstream, armed=armed)
    assert len(resolved.live_ports) == 2


def test_default_combine_wait_policy_wait_armed_requires_armed_outputs() -> None:
    policy = DefaultCombineWaitPolicy(
        ParallelFanInPolicy(wait_mode=WaitMode.WAIT_ARMED, armed_children=frozenset({"a"}))
    )
    upstream = {port_id_for_parallel_child("fan", "a"): None}
    armed = {port_id_for_parallel_child("fan", "a"): True}
    with pytest.raises(EmptyArmingMaskError):
        policy.resolve(upstream={}, armed={})
    with pytest.raises(ArmedInputMissingError):
        policy.resolve(upstream=upstream, armed=armed)


def test_default_arming_overlay_resolves_parallel_fan_in() -> None:
    run = RunIdentity.from_arming(
        experiment_name="exp",
        pipeline_name="pipe",
        pipeline_version="1.0",
        armed_port_ids=[
            port_id_for_parallel_child("fan", "source_a"),
            port_id_for_parallel_child("fan", "source_b"),
        ],
    )
    config = FlowArmingConfig.from_mapping(
        {
            "parallel_policies": {
                "fan": {
                    "wait_mode": "wait_armed",
                    "armed_children": ["source_a", "source_b"],
                }
            }
        }
    )
    overlay = DefaultArmingOverlay.for_parallel_children(
        run_identity=run,
        block_name="fan",
        child_names={
            "source_a": Path("/tmp/a"),
            "source_b": Path("/tmp/b"),
            "source_c": Path("/tmp/c"),
        },
        config=config,
    )
    resolved = overlay.resolve_parallel_fan_in(
        "fan",
        {
            "source_a": Path("/tmp/a"),
            "source_b": Path("/tmp/b"),
            "source_c": Path("/tmp/c"),
        },
    )
    assert {port.path for port in resolved.live_ports} == {Path("/tmp/a"), Path("/tmp/b")}


def test_flow_arming_empty_mapping_is_default() -> None:
    assert FlowArmingConfigType.from_mapping(None) == FlowArmingConfigType()
    assert FlowArmingConfigType.from_mapping({}) == FlowArmingConfigType()
