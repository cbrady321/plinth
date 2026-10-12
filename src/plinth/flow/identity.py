"""Run identity and arming snapshot — lineage authority for armed-set hashing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from plinth.flow.errors import ArmingContractError
from plinth.runtime.hashing import compute_params_hash


def compute_arming_hash(snapshot: "ArmingSnapshot") -> str:
    """Canonical SHA256 of the arming snapshot (same discipline as params_hash)."""
    return compute_params_hash(snapshot.canonical_dict())


@dataclass(frozen=True)
class ArmingSnapshot:
    """Canonical armed-set plus lineage-relevant wait/combine fingerprints for one run."""

    armed_port_ids: tuple[str, ...]
    wait_policy_fingerprint: str = ""
    combine_policy_fingerprint: str = ""

    def __post_init__(self) -> None:
        if len(set(self.armed_port_ids)) != len(self.armed_port_ids):
            raise ArmingContractError("ArmingSnapshot.armed_port_ids must be unique")
        if any(not port_id.strip() for port_id in self.armed_port_ids):
            raise ArmingContractError("ArmingSnapshot.armed_port_ids must be non-blank")

    @classmethod
    def from_port_ids(
        cls,
        armed_port_ids: Iterable[str],
        *,
        wait_policy_fingerprint: str = "",
        combine_policy_fingerprint: str = "",
    ) -> "ArmingSnapshot":
        normalized = tuple(sorted({port_id for port_id in armed_port_ids}))
        return cls(
            armed_port_ids=normalized,
            wait_policy_fingerprint=wait_policy_fingerprint,
            combine_policy_fingerprint=combine_policy_fingerprint,
        )

    @classmethod
    def all_ports(cls, port_ids: Iterable[str]) -> "ArmingSnapshot":
        return cls.from_port_ids(port_ids)

    def canonical_dict(self) -> dict[str, object]:
        return {
            "armed_port_ids": list(self.armed_port_ids),
            "wait_policy_fingerprint": self.wait_policy_fingerprint,
            "combine_policy_fingerprint": self.combine_policy_fingerprint,
        }

    def is_armed(self, port_id: str) -> bool:
        return port_id in self.armed_port_ids

    def armed_subset(self, candidates: Mapping[str, object]) -> tuple[str, ...]:
        return tuple(port_id for port_id in self.armed_port_ids if port_id in candidates)


@dataclass(frozen=True)
class RunIdentity:
    """Information expert for armed-set identity material used in hashes and resume keys."""

    experiment_name: str
    pipeline_name: str
    pipeline_version: str
    arming: ArmingSnapshot

    @classmethod
    def from_arming(
        cls,
        *,
        experiment_name: str,
        pipeline_name: str,
        pipeline_version: str,
        armed_port_ids: Iterable[str],
        wait_policy_fingerprint: str = "",
        combine_policy_fingerprint: str = "",
    ) -> "RunIdentity":
        return cls(
            experiment_name=experiment_name,
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            arming=ArmingSnapshot.from_port_ids(
                armed_port_ids,
                wait_policy_fingerprint=wait_policy_fingerprint,
                combine_policy_fingerprint=combine_policy_fingerprint,
            ),
        )

    def arming_hash(self) -> str:
        return compute_arming_hash(self.arming)

    def resume_key(self) -> str:
        return f"{self.experiment_name}:{self.pipeline_name}:{self.pipeline_version}:{self.arming_hash()}"
