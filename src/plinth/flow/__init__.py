"""First-class flow-control contracts — topology, arming, combine, and run identity."""

from plinth.flow.config import (
    FlowArmingConfig,
    ParallelFanInPolicy,
    fan_in_site_for_block,
    port_id_for_parallel_child,
)
from plinth.flow.errors import (
    ArmedInputMissingError,
    ArmingContractError,
    EmptyArmingMaskError,
    FlowControlError,
    PolicyPairingError,
    UnarmedFanInError,
    WaitAllIncompleteError,
    WaitAllMaskMismatchError,
)
from plinth.flow.identity import ArmingSnapshot, RunIdentity, compute_arming_hash
from plinth.flow.overlay import ArmingOverlay, DefaultArmingOverlay
from plinth.flow.policies import CombineWaitPolicy, DefaultCombineWaitPolicy
from plinth.flow.ports import LiveInputPort, PortAttachment, ResolvedFanIn
from plinth.flow.resume import validate_arming_on_resume
from plinth.flow.types import ArmState, CombineMode, FanInSiteId, PortId, PortReadiness, WaitMode

__all__ = [
    "ArmState",
    "ArmedInputMissingError",
    "ArmingContractError",
    "ArmingOverlay",
    "ArmingSnapshot",
    "CombineMode",
    "CombineWaitPolicy",
    "DefaultArmingOverlay",
    "DefaultCombineWaitPolicy",
    "EmptyArmingMaskError",
    "FanInSiteId",
    "FlowArmingConfig",
    "FlowControlError",
    "LiveInputPort",
    "ParallelFanInPolicy",
    "PolicyPairingError",
    "PortAttachment",
    "PortId",
    "PortReadiness",
    "ResolvedFanIn",
    "RunIdentity",
    "UnarmedFanInError",
    "WaitAllIncompleteError",
    "WaitAllMaskMismatchError",
    "WaitMode",
    "compute_arming_hash",
    "fan_in_site_for_block",
    "port_id_for_parallel_child",
    "validate_arming_on_resume",
]
