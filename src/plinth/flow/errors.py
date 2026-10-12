"""Flow-control contract violations."""

from __future__ import annotations


class FlowControlError(ValueError):
    """Base for flow-control contract failures."""


class ArmingContractError(FlowControlError):
    """Unknown port, duplicate ids, or overlay/run mismatch."""


class EmptyArmingMaskError(ArmingContractError):
    """An arming mask arms zero inputs."""


class UnarmedFanInError(FlowControlError):
    """Wait/combine policy cannot form a live input set."""


class WaitAllIncompleteError(UnarmedFanInError):
    """Wait-all policy: a required child has no output."""


class ArmedInputMissingError(UnarmedFanInError):
    """Wait-armed policy: an armed child has no output."""


class WaitAllMaskMismatchError(ArmingContractError):
    """Wait-all paired with a mask that omits a parallel child."""


class PolicyPairingError(ArmingContractError):
    """Incompatible wait/combine policy configuration."""
