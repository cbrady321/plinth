"""Typed flow-control configuration — orthogonal to DAG topology."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from plinth.flow.errors import EmptyArmingMaskError, PolicyPairingError, WaitAllMaskMismatchError
from plinth.flow.types import CombineMode, FanInSiteId, PortId, WaitMode

if TYPE_CHECKING:
    from plinth.flow.identity import ArmingSnapshot


@dataclass(frozen=True)
class ParallelFanInPolicy:
    """Wait/combine policy for one parallel block fan-in site."""

    wait_mode: WaitMode = WaitMode.WAIT_ALL
    combine_mode: CombineMode = CombineMode.AGGREGATE
    armed_children: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.armed_children is not None and not self.armed_children:
            raise EmptyArmingMaskError(
                f"ParallelFanInPolicy for armed_children={self.armed_children!r} arms zero children"
            )
        if self.wait_mode is WaitMode.WAIT_ALL and self.armed_children is not None:
            raise WaitAllMaskMismatchError(
                "WaitMode.WAIT_ALL requires all parallel children armed; omit armed_children or use WAIT_ARMED"
            )

    def is_child_armed(self, child_name: str) -> bool:
        if self.armed_children is None:
            return True
        return child_name in self.armed_children

    def policy_fingerprint(self) -> str:
        armed = "all" if self.armed_children is None else ",".join(sorted(self.armed_children))
        return f"wait={self.wait_mode.value};combine={self.combine_mode.value};armed={armed}"


@dataclass(frozen=True)
class FlowArmingConfig:
    """
    Run-scoped arming overlay — never stored on PipelineConfig.dag.

    Keys are PortId strings. Omitted ports default to armed when present in topology.
    """

    disarmed_ports: frozenset[str] = field(default_factory=frozenset)
    parallel_policies: dict[str, ParallelFanInPolicy] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "FlowArmingConfig":
        if not data:
            return cls()

        disarmed_raw = data.get("disarmed_ports", [])
        if not isinstance(disarmed_raw, list):
            raise TypeError("flow_arming.disarmed_ports must be a list of port id strings")

        parallel_raw = data.get("parallel_policies", {})
        if not isinstance(parallel_raw, dict):
            raise TypeError("flow_arming.parallel_policies must be a mapping")

        parallel_policies: dict[str, ParallelFanInPolicy] = {}
        for block_name, policy_data in parallel_raw.items():
            if not isinstance(policy_data, dict):
                raise TypeError(f"flow_arming.parallel_policies[{block_name!r}] must be a mapping")
            parallel_policies[str(block_name)] = _parallel_policy_from_dict(policy_data)

        return cls(
            disarmed_ports=frozenset(str(port_id) for port_id in disarmed_raw),
            parallel_policies=parallel_policies,
        )

    def arm_state_for_port(self, port_id: str) -> bool:
        return port_id not in self.disarmed_ports

    def parallel_policy(self, block_name: str) -> ParallelFanInPolicy:
        return self.parallel_policies.get(block_name, ParallelFanInPolicy())

    def armed_port_ids(self, known_port_ids: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            sorted(port_id for port_id in known_port_ids if self.arm_state_for_port(port_id))
        )

    def snapshot(
        self,
        known_port_ids: Iterable[str],
        *,
        wait_policy_fingerprint: str = "",
        combine_policy_fingerprint: str = "",
    ) -> "ArmingSnapshot":
        from plinth.flow.identity import ArmingSnapshot

        return ArmingSnapshot.from_port_ids(
            self.armed_port_ids(known_port_ids),
            wait_policy_fingerprint=wait_policy_fingerprint,
            combine_policy_fingerprint=combine_policy_fingerprint,
        )


def _parallel_policy_from_dict(data: Mapping[str, Any]) -> ParallelFanInPolicy:
    wait_raw = data.get("wait_mode", WaitMode.WAIT_ALL.value)
    combine_raw = data.get("combine_mode", CombineMode.AGGREGATE.value)
    armed_raw = data.get("armed_children")

    try:
        wait_mode = WaitMode(str(wait_raw))
    except ValueError as exc:
        raise PolicyPairingError(f"Unknown wait_mode {wait_raw!r}") from exc

    try:
        combine_mode = CombineMode(str(combine_raw))
    except ValueError as exc:
        raise PolicyPairingError(f"Unknown combine_mode {combine_raw!r}") from exc

    armed_children: frozenset[str] | None
    if armed_raw is None:
        armed_children = None
    elif isinstance(armed_raw, list):
        armed_children = frozenset(str(name) for name in armed_raw)
    else:
        raise TypeError("armed_children must be a list of child names or null")

    return ParallelFanInPolicy(
        wait_mode=wait_mode,
        combine_mode=combine_mode,
        armed_children=armed_children,
    )


def port_id_for_parallel_child(block_name: str, child_name: str) -> PortId:
    return PortId(f"{block_name}/{child_name}")


def fan_in_site_for_block(block_name: str) -> FanInSiteId:
    return FanInSiteId(block_name)
