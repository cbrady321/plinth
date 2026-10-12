"""Resolved live inputs after overlay filtering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from plinth.flow.types import PortId, PortReadiness


@dataclass(frozen=True)
class LiveInputPort:
    """One armed, path-resolved upstream contribution."""

    port_id: PortId
    path: Path
    lineage_token: str = ""

    def __post_init__(self) -> None:
        if not str(self.port_id).strip():
            raise ValueError("LiveInputPort.port_id must be non-blank")


@dataclass(frozen=True)
class ResolvedFanIn:
    """Fan-in result passed to combine or downstream stage execution."""

    live_ports: tuple[LiveInputPort, ...]

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(port.path for port in self.live_ports)

    def __bool__(self) -> bool:
        return bool(self.live_ports)


@dataclass(frozen=True)
class PortAttachment:
    """Topology attachment with explicit readiness — disarmed ≠ empty ≠ unconnected."""

    port_id: PortId
    readiness: PortReadiness
    path: Path | None = None

    @property
    def is_live(self) -> bool:
        return self.readiness is PortReadiness.ARMED and self.path is not None
