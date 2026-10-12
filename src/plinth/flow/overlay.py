"""Executor-facing arming overlay — consulted before fan-in, not on Block.execute."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

from plinth.flow.config import FlowArmingConfig, port_id_for_parallel_child
from plinth.flow.errors import ArmingContractError, FlowControlError, UnarmedFanInError
from plinth.flow.identity import RunIdentity
from plinth.flow.policies import CombineWaitPolicy, DefaultCombineWaitPolicy
from plinth.flow.ports import ResolvedFanIn
from plinth.flow.types import ArmState, FanInSiteId, PortId


@runtime_checkable
class ArmingOverlay(Protocol):
    """
    Run-scoped arming view consulted by block executors before fan-in.

    Does not own DAG topology or resume persistence.
    """

    @property
    def run_identity(self) -> RunIdentity: ...

    def arm_state(self, port_id: PortId) -> ArmState:
        """Raises ArmingContractError when port_id is unknown to this overlay."""
        ...

    def resolve_fan_in(
        self,
        fan_in_site: FanInSiteId,
        upstream: Mapping[PortId, Path | None],
        policy: CombineWaitPolicy,
    ) -> ResolvedFanIn:
        """Filter to armed live ports under explicit wait/combine policy."""
        ...


@dataclass
class DefaultArmingOverlay:
    """Overlay backed by FlowArmingConfig and RunIdentity."""

    run_identity: RunIdentity
    config: FlowArmingConfig = field(default_factory=FlowArmingConfig)
    _known_ports: frozenset[str] = field(default_factory=frozenset)

    def register_ports(self, port_ids: Mapping[PortId, Path | None]) -> None:
        self._known_ports = frozenset({*self._known_ports, *port_ids.keys()})

    def arm_state(self, port_id: PortId) -> ArmState:
        if self._known_ports and str(port_id) not in self._known_ports:
            raise ArmingContractError(f"Unknown port_id {port_id!r} for overlay")
        if self.config.arm_state_for_port(str(port_id)):
            return ArmState.ARMED
        return ArmState.UNARMED

    def arm_state_for_parallel_child(self, block_name: str, child_name: str) -> ArmState:
        port_id = port_id_for_parallel_child(block_name, child_name)
        if not self.config.arm_state_for_port(str(port_id)):
            return ArmState.UNARMED
        if not self.config.parallel_policy(block_name).is_child_armed(child_name):
            return ArmState.UNARMED
        return ArmState.ARMED

    def armed_map(self, upstream: Mapping[PortId, Path | None]) -> dict[PortId, bool]:
        return {port_id: self.arm_state(port_id) is ArmState.ARMED for port_id in upstream}

    def armed_map_for_parallel(
        self,
        block_name: str,
        upstream: Mapping[PortId, Path | None],
    ) -> dict[PortId, bool]:
        armed: dict[PortId, bool] = {}
        for port_id in upstream:
            child_name = str(port_id).split("/", 1)[-1]
            armed[port_id] = self.arm_state_for_parallel_child(block_name, child_name) is ArmState.ARMED
        return armed

    def resolve_fan_in(
        self,
        fan_in_site: FanInSiteId,
        upstream: Mapping[PortId, Path | None],
        policy: CombineWaitPolicy,
    ) -> ResolvedFanIn:
        armed = self.armed_map(upstream)
        try:
            return policy.resolve(upstream=upstream, armed=armed)
        except FlowControlError:
            raise
        except Exception as exc:
            raise UnarmedFanInError(
                f"Fan-in site {fan_in_site!r} could not resolve live inputs: {exc}"
            ) from exc

    def policy_for_parallel_block(self, block_name: str) -> DefaultCombineWaitPolicy:
        return DefaultCombineWaitPolicy(self.config.parallel_policy(block_name))

    @classmethod
    def for_parallel_children(
        cls,
        *,
        run_identity: RunIdentity,
        block_name: str,
        child_names: Mapping[str, Path | None],
        config: FlowArmingConfig | None = None,
    ) -> "DefaultArmingOverlay":
        flow_config = config or FlowArmingConfig()
        upstream = {
            port_id_for_parallel_child(block_name, child_name): path
            for child_name, path in child_names.items()
        }
        overlay = cls(run_identity=run_identity, config=flow_config)
        overlay.register_ports(upstream)
        return overlay

    def resolve_parallel_fan_in(
        self,
        block_name: str,
        child_outputs: Mapping[str, Path | None],
    ) -> ResolvedFanIn:
        upstream = {
            port_id_for_parallel_child(block_name, child_name): path
            for child_name, path in child_outputs.items()
        }
        self.register_ports(upstream)
        policy = self.policy_for_parallel_block(block_name)
        armed = self.armed_map_for_parallel(block_name, upstream)
        return policy.resolve(upstream=upstream, armed=armed)
