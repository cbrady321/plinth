"""Pipeline run wiring for flow-control contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from plinth.blocks import Block, ParallelBlock, SequentialBlock
from plinth.flow.config import FlowArmingConfig, port_id_for_parallel_child
from plinth.flow.identity import RunIdentity
from plinth.flow.overlay import DefaultArmingOverlay

if TYPE_CHECKING:
    from plinth.config import PipelineConfig

FLOW_RUN_CONTEXT_KEY = "_flow_run_context"
FLOW_ARMING_HASH_KEY = "_flow_arming_hash"


@dataclass(frozen=True)
class FlowRunContext:
    """Run-scoped flow state injected into the DAG config dict (not YAML)."""

    run_identity: RunIdentity
    overlay: DefaultArmingOverlay


def flow_arming_is_active(flow_arming: FlowArmingConfig) -> bool:
    return bool(flow_arming.disarmed_ports or flow_arming.parallel_policies)


def collect_parallel_port_ids(dag_root: Block) -> tuple[str, ...]:
    ports: set[str] = set()

    def walk(node: Block) -> None:
        if isinstance(node, ParallelBlock):
            for child in node.children:
                ports.add(str(port_id_for_parallel_child(node.name, child.name)))
                walk(child)
        elif isinstance(node, SequentialBlock):
            for child in node.children:
                walk(child)

    walk(dag_root)
    return tuple(sorted(ports))


def _policy_fingerprint(flow_arming: FlowArmingConfig) -> str:
    if not flow_arming.parallel_policies:
        return ""
    return ";".join(
        f"{block_name}:{policy.policy_fingerprint()}"
        for block_name, policy in sorted(flow_arming.parallel_policies.items())
    )


def build_flow_run_context(
    config: PipelineConfig,
    experiment_name: str,
    dag_root: Block,
) -> FlowRunContext | None:
    if not flow_arming_is_active(config.flow_arming):
        return None

    known_ports = collect_parallel_port_ids(dag_root)
    fingerprint = _policy_fingerprint(config.flow_arming)
    run_identity = RunIdentity(
        experiment_name=experiment_name,
        pipeline_name=config.name,
        pipeline_version=config.version,
        arming=config.flow_arming.snapshot(
            known_ports,
            wait_policy_fingerprint=fingerprint,
            combine_policy_fingerprint=fingerprint,
        ),
    )
    overlay = DefaultArmingOverlay(run_identity=run_identity, config=config.flow_arming)
    return FlowRunContext(run_identity=run_identity, overlay=overlay)


def attach_flow_run_context(dag_root: Block, flow_context: FlowRunContext | None) -> None:
    if flow_context is None:
        dag_root.config.pop(FLOW_RUN_CONTEXT_KEY, None)
        dag_root.config[FLOW_ARMING_HASH_KEY] = ""
        return
    dag_root.config[FLOW_RUN_CONTEXT_KEY] = flow_context
    dag_root.config[FLOW_ARMING_HASH_KEY] = flow_context.run_identity.arming_hash()


def get_flow_run_context(config_dict: dict[str, Any]) -> FlowRunContext | None:
    context = config_dict.get(FLOW_RUN_CONTEXT_KEY)
    if isinstance(context, FlowRunContext):
        return context
    return None


def get_flow_arming_hash(config_dict: dict[str, Any]) -> str:
    value = config_dict.get(FLOW_ARMING_HASH_KEY, "")
    return value if isinstance(value, str) else ""
