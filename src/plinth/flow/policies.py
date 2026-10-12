"""Wait and combine policy protocols with typed defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

from plinth.flow.config import ParallelFanInPolicy
from plinth.flow.errors import (
    ArmedInputMissingError,
    EmptyArmingMaskError,
    WaitAllIncompleteError,
)
from plinth.flow.ports import LiveInputPort, ResolvedFanIn
from plinth.flow.types import PortId, WaitMode


@runtime_checkable
class CombineWaitPolicy(Protocol):
    """How to wait for and select armed upstream ports at a fan-in site."""

    def resolve(
        self,
        *,
        upstream: Mapping[PortId, Path | None],
        armed: Mapping[PortId, bool],
    ) -> ResolvedFanIn:
        """
        Pre: upstream keys are wired ports; armed covers upstream keys.
        Post: every returned LiveInputPort is armed with a resolved path.
        """
        ...


@dataclass(frozen=True)
class DefaultCombineWaitPolicy:
    """Policy driven by ParallelFanInPolicy wait/combine settings."""

    policy: ParallelFanInPolicy

    def resolve(
        self,
        *,
        upstream: Mapping[PortId, Path | None],
        armed: Mapping[PortId, bool],
    ) -> ResolvedFanIn:
        armed_upstream = {
            port_id: path for port_id, path in upstream.items() if armed.get(port_id, False)
        }
        if not armed_upstream and self.policy.wait_mode is WaitMode.WAIT_ARMED:
            raise EmptyArmingMaskError("No armed upstream ports at fan-in site")

        if self.policy.wait_mode is WaitMode.WAIT_ALL:
            missing = [port_id for port_id, path in upstream.items() if path is None]
            if missing:
                raise WaitAllIncompleteError(
                    f"Wait-all fan-in missing outputs for ports: {', '.join(sorted(missing))}"
                )
            selected = upstream
        else:
            missing_armed = [
                port_id for port_id, path in armed_upstream.items() if path is None
            ]
            if missing_armed:
                raise ArmedInputMissingError(
                    f"Armed fan-in missing outputs for ports: {', '.join(sorted(missing_armed))}"
                )
            selected = armed_upstream

        live_ports = tuple(
            LiveInputPort(port_id=port_id, path=path)
            for port_id, path in selected.items()
            if path is not None
        )
        return ResolvedFanIn(live_ports=live_ports)
