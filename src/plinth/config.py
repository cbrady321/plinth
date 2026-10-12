"""Pipeline configuration with YAML support."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from plinth.blocks import Block, build_dag_from_dict
from plinth.flow.config import FlowArmingConfig
from plinth.validation import ValidationResult, validate_pipeline_config


@dataclass
class PipelineConfig:
    """Pipeline configuration from YAML."""

    name: str
    version: str
    # DAG-based definition (Python dict)
    dag: Optional[Dict[str, Any]] = None
    params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    input_source: str = ""
    # Deprecated no-ops: read and written back unchanged, ignored by the runtime.
    hierarchy_enabled: bool = False
    hierarchy_schema: Optional[Dict[str, Any]] = None
    export_flags: Dict[str, bool] = field(default_factory=dict)
    block_settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    status: str = "active"
    # JSONPath-based selective execution controls
    start_from_paths: List[str] = field(default_factory=list)
    end_at_paths: List[str] = field(default_factory=list)
    # Parallel error handling policy: 'fail_fast' or 'continue'
    parallel_error_policy: str = "fail_fast"
    # Debug switch to force copying input data forward if not modified
    always_propagate: bool = False
    # Run-scoped arming overlay — orthogonal to dag topology and start/end window
    flow_arming: FlowArmingConfig = field(default_factory=FlowArmingConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "PipelineConfig":
        """Load pipeline config from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        return cls(
            name=data["name"],
            version=data["version"],
            dag=data.get("dag"),
            params=data.get("params", {}),
            input_source=data.get("input_source", ""),
            hierarchy_enabled=data.get("hierarchy_enabled", False),
            hierarchy_schema=data.get("hierarchy_schema") or None,
            export_flags=data.get("export_flags", {}),
            block_settings=data.get("block_settings", {}),
            status=data.get("status", "active"),
            start_from_paths=data.get("start_from_paths", data.get("start_from_stage", [])),
            end_at_paths=data.get("end_at_paths", data.get("end_at_stage", [])),
            parallel_error_policy=data.get("parallel_error_policy", "fail_fast"),
            always_propagate=data.get("always_propagate", False),
            flow_arming=FlowArmingConfig.from_mapping(data.get("flow_arming")),
        )

    def to_yaml(self, path: Path) -> None:
        """Save pipeline config to YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "name": self.name,
            "version": self.version,
            "dag": self.dag,
            "params": self.params,
            "input_source": self.input_source,
            "hierarchy_enabled": self.hierarchy_enabled,
            "hierarchy_schema": self.hierarchy_schema,
            "export_flags": self.export_flags,
            "block_settings": self.block_settings,
            "status": self.status,
            "start_from_paths": self.start_from_paths,
            "end_at_paths": self.end_at_paths,
            "parallel_error_policy": self.parallel_error_policy,
            "always_propagate": self.always_propagate,
            "flow_arming": _flow_arming_to_dict(self.flow_arming),
        }

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def build_dag(self) -> Block:
        """Build the DAG block tree from the configured dictionary."""
        if not self.dag:
            raise ValueError("PipelineConfig.dag must be provided for DAG execution")
        # Provide params/export_flags into config dict for StageNode access
        config_dict: Dict[str, Any] = {
            "params": self.params,
            "export_flags": self.export_flags,
            "_block_settings": self.block_settings,
            "name": self.name,
            "version": self.version,
            "always_propagate": self.always_propagate,
            "parallel_error_policy": self.parallel_error_policy,
        }
        return build_dag_from_dict(self.dag, config_dict)

    def validate(self) -> ValidationResult:
        return validate_pipeline_config(self)


def _flow_arming_to_dict(config: FlowArmingConfig) -> dict[str, object]:
    if not config.disarmed_ports and not config.parallel_policies:
        return {}
    parallel_policies: dict[str, dict[str, object]] = {}
    for block_name, policy in config.parallel_policies.items():
        parallel_policies[block_name] = {
            "wait_mode": policy.wait_mode.value,
            "combine_mode": policy.combine_mode.value,
            "armed_children": sorted(policy.armed_children) if policy.armed_children is not None else None,
        }
    return {
        "disarmed_ports": sorted(config.disarmed_ports),
        "parallel_policies": parallel_policies,
    }
