"""Pipeline configuration validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from plinth.blocks import ParallelBlock, SequentialBlock, StageNode
from plinth.registry import StageRegistry

if TYPE_CHECKING:
    from plinth.blocks import Block
    from plinth.config import PipelineConfig


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _collect_stage_names(block: Block) -> list[str]:
    return block.get_all_stage_names()


def _collect_stage_names_in_order(block: Block) -> list[str]:
    ordered: list[str] = []
    for child in block.children:
        if isinstance(child, StageNode):
            ordered.append(child.name)
        else:
            ordered.extend(_collect_stage_names_in_order(child))
    return ordered


def _validate_stage_params(config: PipelineConfig, dag_root: Block, errors: list[str]) -> None:
    for index, stage_name in enumerate(_collect_stage_names_in_order(dag_root)):
        schema = StageRegistry.get_param_schema(stage_name)
        if schema is None:
            continue
        params = config.params.get(stage_name, {})
        if not isinstance(params, dict):
            errors.append(f"stages[{index}].params: must be a mapping")
            continue
        prefix = f"stages[{index}].params"
        errors.extend(schema.validate(params, prefix))


def _check_parallel_conflicts(block: Block, path: str, errors: list[str]) -> None:
    if isinstance(block, ParallelBlock):
        aggregate_outputs = True
        settings = block.config.get("_block_settings", {})
        if isinstance(settings, dict):
            block_settings = settings.get(block.name, {})
            if isinstance(block_settings, dict):
                aggregate_outputs = block_settings.get("aggregate_outputs", True)

        if aggregate_outputs:
            written_map: dict[str, str] = {}
            for child in block.children:
                for col in child.get_written_columns():
                    if col in written_map:
                        errors.append(
                            f"{path}: parallel conflict — column '{col}' written by "
                            f"'{written_map[col]}' and '{child.name}'"
                        )
                    else:
                        written_map[col] = child.name
                key_mods = child.get_unique_key_modifications()
                if key_mods:
                    errors.append(f"{path}: parallel branch '{child.name}' appends to unique key {key_mods}")

    for idx, child in enumerate(block.children):
        child_path = f"{path}.children[{idx}]"
        _check_parallel_conflicts(child, child_path, errors)


def _collect_parallel_sites(block: Block) -> dict[str, list[str]]:
    sites: dict[str, list[str]] = {}

    def walk(node: Block) -> None:
        if isinstance(node, ParallelBlock):
            sites[node.name] = [child.name for child in node.children]
            for child in node.children:
                walk(child)
        elif isinstance(node, SequentialBlock):
            for child in node.children:
                walk(child)

    walk(block)
    return sites


def _validate_flow_arming(config: PipelineConfig, dag_root: Block, errors: list[str]) -> None:
    from plinth.flow.config import port_id_for_parallel_child
    from plinth.flow.runtime import collect_parallel_port_ids, flow_arming_is_active

    if not flow_arming_is_active(config.flow_arming):
        return

    known_ports = set(collect_parallel_port_ids(dag_root))
    parallel_sites = _collect_parallel_sites(dag_root)

    for port_id in sorted(config.flow_arming.disarmed_ports):
        if port_id not in known_ports:
            errors.append(f"flow_arming.disarmed_ports: unknown port {port_id!r}")

    for block_name, policy in sorted(config.flow_arming.parallel_policies.items()):
        child_names = parallel_sites.get(block_name)
        if child_names is None:
            errors.append(f"flow_arming.parallel_policies: unknown parallel block {block_name!r}")
            continue
        children = set(child_names)
        if policy.armed_children is None:
            continue
        unknown_children = sorted(policy.armed_children - children)
        if unknown_children:
            errors.append(
                f"flow_arming.parallel_policies[{block_name!r}].armed_children: "
                f"unknown child name(s) {unknown_children}"
            )
        if not policy.armed_children & children:
            errors.append(
                f"flow_arming.parallel_policies[{block_name!r}].armed_children: "
                "must arm at least one parallel child"
            )

    armed_via_policy = {
        str(port_id_for_parallel_child(block_name, child_name))
        for block_name, policy in config.flow_arming.parallel_policies.items()
        if policy.armed_children is not None
        for child_name in policy.armed_children
        if block_name in parallel_sites and child_name in parallel_sites[block_name]
    }
    disarmed_via_ports = known_ports - set(
        port_id
        for port_id in known_ports
        if config.flow_arming.arm_state_for_port(port_id)
    )
    if armed_via_policy and disarmed_via_ports and armed_via_policy & disarmed_via_ports:
        overlap = sorted(armed_via_policy & disarmed_via_ports)
        errors.append(
            "flow_arming: port(s) both disarmed via disarmed_ports and armed via "
            f"parallel_policies.armed_children: {overlap}"
        )


def validate_pipeline_config(config: PipelineConfig) -> ValidationResult:
    errors: list[str] = []

    if not config.dag:
        errors.append("dag: PipelineConfig.dag must be provided")
        return ValidationResult(errors)

    try:
        dag_root = config.build_dag()
    except ValueError as exc:
        errors.append(str(exc))
        return ValidationResult(errors)
    except Exception as exc:
        errors.append(f"dag: {exc}")
        return ValidationResult(errors)

    registered = set(StageRegistry.list_stages())
    for stage_name in _collect_stage_names(dag_root):
        if stage_name not in registered:
            errors.append(f"stage '{stage_name}' is not registered")
    if errors:
        # The remaining checks read each stage's intent and parameter schema from the registry.
        errors.append(f"registered stages: {sorted(registered) or 'none (import your stage modules first)'}")
        return ValidationResult(errors)

    _check_parallel_conflicts(dag_root, "$.dag", errors)
    _validate_stage_params(config, dag_root, errors)
    _validate_flow_arming(config, dag_root, errors)
    return ValidationResult(errors)
