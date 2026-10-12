"""Registry for dynamically loading pipeline stage classes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

StageMode = Literal["typical", "exceptional"]

EXCEPTIONAL_STAGES: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SidecarArtifact:
    filename: str
    description: str


@dataclass
class ExceptionalObligations:
    records_ledger: bool = True
    hands_off_manifest: bool = True
    uses_resolver_address: bool = True


@dataclass
class ExceptionalMetadata:
    sidecar_artifacts: list[SidecarArtifact] = field(default_factory=list)
    obligations: ExceptionalObligations = field(default_factory=ExceptionalObligations)


EXCEPTIONAL_METADATA: dict[str, ExceptionalMetadata] = {}


class StageRegistry:
    """Registry for dynamically loading stage classes."""

    _stages: Dict[str, type] = {}
    _modes: Dict[str, StageMode] = {}
    _exceptional_metadata: Dict[str, ExceptionalMetadata] = {}
    _param_schemas: Dict[str, Any] = {}

    @classmethod
    def register(
        cls,
        name: str,
        *,
        mode: StageMode = "typical",
        obligations: Optional[ExceptionalObligations] = None,
        sidecar_artifacts: Optional[list[SidecarArtifact]] = None,
    ) -> Callable[[type], type]:
        if mode == "typical" and name in EXCEPTIONAL_STAGES:
            mode = "exceptional"

        def decorator(stage_class: type) -> type:
            cls._stages[name] = stage_class
            cls._modes[name] = mode
            if mode == "exceptional":
                meta = EXCEPTIONAL_METADATA.get(name, ExceptionalMetadata())
                if obligations is not None:
                    meta = ExceptionalMetadata(
                        sidecar_artifacts=meta.sidecar_artifacts,
                        obligations=obligations,
                    )
                if sidecar_artifacts is not None:
                    meta = ExceptionalMetadata(
                        sidecar_artifacts=sidecar_artifacts,
                        obligations=meta.obligations,
                    )
                cls._exceptional_metadata[name] = meta
            logger.debug(f"Registered stage: {name} ({mode}) -> {stage_class.__name__}")
            return stage_class

        return decorator

    @classmethod
    def get_stage(cls, name: str) -> type:
        if name not in cls._stages:
            raise KeyError(f"Stage '{name}' not found in registry. Available stages: {cls.list_stages()}")
        return cls._stages[name]

    @classmethod
    def get_mode(cls, name: str) -> StageMode:
        return cls._modes.get(name, "typical")

    @classmethod
    def list_stages(cls) -> List[str]:
        return list(cls._stages.keys())

    @classmethod
    def get_exceptional_metadata(cls, name: str) -> Optional[ExceptionalMetadata]:
        return cls._exceptional_metadata.get(name)

    @classmethod
    def list_exceptional(cls) -> List[str]:
        return sorted(name for name, mode in cls._modes.items() if mode == "exceptional")

    @classmethod
    def register_param_schema(cls, name: str, schema: Any) -> None:
        cls._param_schemas[name] = schema

    @classmethod
    def get_param_schema(cls, name: str) -> Optional[Any]:
        return cls._param_schemas.get(name)

    @classmethod
    def list_param_schemas(cls) -> List[str]:
        return sorted(cls._param_schemas.keys())

    @classmethod
    def unregister(cls, name: str) -> None:
        if name in cls._stages:
            del cls._stages[name]
            cls._modes.pop(name, None)
            cls._exceptional_metadata.pop(name, None)
            logger.debug(f"Unregistered stage: {name}")

    @classmethod
    def clear(cls) -> None:
        cls._stages.clear()
        cls._modes.clear()
        cls._exceptional_metadata.clear()
        cls._param_schemas.clear()
