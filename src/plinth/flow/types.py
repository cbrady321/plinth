"""Shared value types for flow-control contracts."""

from __future__ import annotations

from enum import Enum
from typing import NewType

PortId = NewType("PortId", str)
"""Stable topological input port key (block path + child name or index)."""

FanInSiteId = NewType("FanInSiteId", str)
"""Fan-in site where multiple upstream ports are combined before downstream execution."""


class PortReadiness(str, Enum):
    """Three distinct input states — not interchangeable."""

    UNCONNECTED = "unconnected"
    DISARMED = "disarmed"
    ARMED = "armed"


class ArmState(str, Enum):
    """Arming overlay view of a wired port."""

    ARMED = "armed"
    UNARMED = "unarmed"


class WaitMode(str, Enum):
    """When a parallel fan-in may proceed to combine."""

    WAIT_ALL = "wait_all"
    WAIT_ARMED = "wait_armed"


class CombineMode(str, Enum):
    """How armed branch outputs are merged at a fan-in site."""

    AGGREGATE = "aggregate"
    PASSTHROUGH = "passthrough"
