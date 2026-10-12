"""Block execute implementations extracted from blocks.py for topology-only dispatch."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

from plinth.context import FileSystemStageContext, MultiInputStageContext
from plinth.flow.runtime import get_flow_run_context
from plinth.flow.types import ArmState, CombineMode
from plinth.runtime.hashing import compute_directory_hash
from plinth.runtime.ledger_writer import LedgerWriter

if TYPE_CHECKING:
    from plinth.block_dag import BlockExecutionResult, ExecutionConstraints
    from plinth.blocks import ParallelBlock, SequentialBlock, StageNode

logger = logging.getLogger(__name__)


def _aggregate_block_outputs(
    block_name: str,
    block_type: str,
    input_dirs: List[Path],
    block_dir: Path,
) -> BlockExecutionResult:
    from plinth.block_dag import BlockExecutionResult

    agg_context = MultiInputStageContext(
        input_dirs=input_dirs,
        output_dir=block_dir,
        manifest=None,
    )
    merged_manifest = agg_context.get_manifest()
    if merged_manifest:
        agg_context.update_manifest(merged_manifest, replace=True)
        logger.info(f"Aggregated manifest with {len(merged_manifest)} rows to {block_dir}")

    merged_schema = agg_context.get_schema()
    if merged_schema:
        agg_context.save_schema(merged_schema)

    merged_ledger = agg_context.get_ledger()
    writer = LedgerWriter()
    writer.record_aggregation(
        merged_ledger,
        block_name=block_name,
        input_hashes=[compute_directory_hash(directory) for directory in input_dirs],
        output_hash=compute_directory_hash(block_dir),
    )
    writer.write(merged_ledger, block_dir)

    return BlockExecutionResult(
        output_dirs=[block_dir],
        block_name=block_name,
        block_type=block_type,
    )


def execute_sequential_block(
    block: SequentialBlock,
    input_dirs: List[Path],
    parent_output_dir: Path,
    prefix: Optional[Union[int, str]],
    constraints: Optional[ExecutionConstraints] = None,
    current_index_path: Optional[List[int]] = None,
    parent_location_code: str = "",
    sequential_counter: Optional[List[int]] = None,
) -> BlockExecutionResult:
    from plinth.block_dag import BlockExecutionResult
    from plinth.blocks import ParallelBlock

    logger.info(f"Executing sequential block: {block.name}")

    if prefix and isinstance(prefix, str):
        location_code = block._build_location_code(prefix, parent_location_code)
        block_dir_name = block.get_block_directory_name(prefix, location_code)
    else:
        if sequential_counter is None:
            sequential_counter = [1]
        block_num = sequential_counter[0]
        sequential_counter[0] += 1
        block_dir_name = f"{block_num:02d}_{block.name}"
        location_code = ""

    block_dir = parent_output_dir / block_dir_name
    block_dir.mkdir(parents=True, exist_ok=True)

    current_inputs = input_dirs
    for i, child in enumerate(block.children):
        child_index_path = (current_index_path or []) + [i]

        if constraints and constraints.is_before_start(child_index_path):
            logger.info(f"⏭️ Skipping stage/block '{child.name}' (before start stage)")

            child_dir_name = ""
            if isinstance(child, ParallelBlock):
                child_num = sequential_counter[0] if sequential_counter else 1
                child_dir_name = f"{child_num:02d}_{child.name}"
                if sequential_counter:
                    sequential_counter[0] += 1
            else:
                if parent_location_code and isinstance(prefix, str):
                    branch_counters_key = f"_branch_counters_{location_code}"
                    if branch_counters_key not in block.config:
                        block.config[branch_counters_key] = [1]
                    branch_counter = block.config[branch_counters_key]
                    stage_num = branch_counter[0]
                    branch_counter[0] += 1
                    child_location_code = location_code + f"{stage_num:02d}"
                    child_dir_name = f"{child_location_code}_{child.name}"
                else:
                    if sequential_counter is None:
                        sequential_counter = [1]
                    child_num = sequential_counter[0]
                    sequential_counter[0] += 1
                    child_dir_name = f"{child_num:02d}_{child.name}"

            skipped_output_dir = parent_output_dir / child_dir_name
            if not skipped_output_dir.exists():
                error_msg = (
                    f"❌ Skipped block '{child.name}' output directory not found at {skipped_output_dir}\n"
                    f"   This is required because the pipeline starts from a later stage.\n"
                    "   To fix: either rerun the pipeline from an earlier stage, "
                    "or adjust 'start_from_paths' in your config."
                )
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            current_inputs = [skipped_output_dir]
            continue

        if isinstance(child, ParallelBlock):
            child_num = sequential_counter[0] if sequential_counter else 1
            if sequential_counter:
                sequential_counter[0] += 1
            result = child.execute(
                current_inputs,
                parent_output_dir,
                child_num,
                constraints=constraints,
                current_index_path=child_index_path,
                parent_location_code="",
                sequential_counter=sequential_counter,
            )
        else:
            child_parent_code = location_code if location_code else ""
            result = child.execute(
                current_inputs,
                parent_output_dir,
                None,
                constraints=constraints,
                current_index_path=child_index_path,
                parent_location_code=child_parent_code,
                sequential_counter=sequential_counter,
            )
        current_inputs = result.output_dirs
        if constraints and constraints.is_end_here(child_index_path):
            break

    if current_inputs and block._get_block_setting("aggregate_outputs", True):
        try:
            return _aggregate_block_outputs(
                block.name,
                "sequential",
                current_inputs,
                block_dir,
            )
        except Exception as e:
            logger.error(f"Failed to propagate outputs in sequential block '{block.name}': {e}")

    return BlockExecutionResult(
        output_dirs=current_inputs,
        block_name=block.name,
        block_type="sequential",
    )


def _parallel_aggregate_enabled(block: ParallelBlock) -> bool:
    flow_context = get_flow_run_context(block.config)
    if flow_context is not None:
        policy = flow_context.overlay.config.parallel_policy(block.name)
        return policy.combine_mode is CombineMode.AGGREGATE
    return bool(block._get_block_setting("aggregate_outputs", True))


def _parallel_child_is_armed(block: ParallelBlock, child_name: str) -> bool:
    flow_context = get_flow_run_context(block.config)
    if flow_context is None:
        return True
    return (
        flow_context.overlay.arm_state_for_parallel_child(block.name, child_name) is ArmState.ARMED
    )


def execute_parallel_block(
    block: ParallelBlock,
    input_dirs: List[Path],
    parent_output_dir: Path,
    prefix: Optional[Union[int, str]],
    constraints: Optional[ExecutionConstraints] = None,
    current_index_path: Optional[List[int]] = None,
    parent_location_code: str = "",
    sequential_counter: Optional[List[int]] = None,
) -> BlockExecutionResult:
    from plinth.block_dag import BlockExecutionResult

    logger.info(f"Executing parallel block: {block.name}")

    if prefix is None:
        raise ValueError("Parallel blocks require a prefix")

    if isinstance(prefix, int):
        block_dir_name = f"{prefix:02d}_{block.name}"
        location_code = f"{prefix:02d}"
    else:
        location_code = block._build_location_code(prefix, parent_location_code)
        block_dir_name = block.get_block_directory_name(prefix, location_code)
    block_dir = parent_output_dir / block_dir_name
    block_dir.mkdir(parents=True, exist_ok=True)

    aggregate_outputs = _parallel_aggregate_enabled(block)
    written_map: dict[str, str] = {}
    for child in block.children:
        if not _parallel_child_is_armed(block, child.name):
            continue
        if aggregate_outputs:
            cols = child.get_written_columns()
            for column in cols:
                if column in written_map:
                    raise ValueError(
                        f"Parallel conflict in block '{block.name}': "
                        f"Column '{column}' is written by both '{written_map[column]}' and '{child.name}'. "
                        "Parallel branches must modify disjoint sets of columns when aggregate_outputs=True."
                    )
                written_map[column] = child.name

        key_mods = child.get_unique_key_modifications()
        if key_mods:
            raise ValueError(
                f"Invalid intent in parallel branch '{child.name}' of block '{block.name}': "
                f"Attempting to append to unique key: {key_mods}. "
                "Structural changes (expanding rows/keys) must be done in Sequential blocks, "
                "not Parallel blocks."
            )

    all_outputs: List[Path] = []
    child_outputs: dict[str, Path | None] = {}
    errors: List[str] = []
    for i, child in enumerate(block.children):
        child_prefix = chr(ord("a") + i)
        child_index_path = (current_index_path or []) + [i]
        if constraints and constraints.has_any_end_paths():
            if not constraints.is_relevant_subtree(child_index_path):
                logger.info(f"Skipping parallel branch '{child.name}' (no relevant end_at_paths)")
                continue
        if not _parallel_child_is_armed(block, child.name):
            logger.info(f"Skipping parallel branch '{child.name}' (disarmed by flow_arming)")
            child_outputs[child.name] = None
            continue
        try:
            if isinstance(prefix, str) and parent_location_code:
                child_parent_code = location_code
            elif isinstance(prefix, int):
                child_parent_code = location_code
            else:
                child_parent_code = ""
            result = child.execute(
                input_dirs,
                parent_output_dir,
                child_prefix,
                constraints=constraints,
                current_index_path=child_index_path,
                parent_location_code=child_parent_code,
                sequential_counter=sequential_counter,
            )
            all_outputs.extend(result.output_dirs)
            child_outputs[child.name] = result.output_dirs[0] if result.output_dirs else None
        except Exception as e:
            policy = block.config.get("parallel_error_policy", "fail_fast")
            msg = f"Parallel branch '{child.name}' failed: {e}"
            if policy == "continue":
                logger.error(msg)
                errors.append(msg)
                continue
            if policy == "continue":
                logger.error(msg)
                errors.append(msg)
                child_outputs[child.name] = None
                continue
            raise

    flow_context = get_flow_run_context(block.config)
    if flow_context is not None:
        resolved = flow_context.overlay.resolve_parallel_fan_in(block.name, child_outputs)
        live_paths = list(resolved.paths)
        if aggregate_outputs and live_paths:
            try:
                return _aggregate_block_outputs(
                    block.name,
                    "parallel",
                    live_paths,
                    block_dir,
                )
            except Exception as e:
                logger.error(f"Failed to aggregate parallel outputs in block '{block.name}': {e}")
                raise
        return BlockExecutionResult(
            output_dirs=live_paths,
            block_name=block.name,
            block_type="parallel",
        )

    if all_outputs and aggregate_outputs:
        try:
            return _aggregate_block_outputs(
                block.name,
                "parallel",
                all_outputs,
                block_dir,
            )
        except Exception as e:
            logger.error(f"Failed to aggregate parallel outputs in block '{block.name}': {e}")
            raise

    return BlockExecutionResult(
        output_dirs=all_outputs,
        block_name=block.name,
        block_type="parallel",
    )


def execute_stage_node(
    block: StageNode,
    input_dirs: List[Path],
    parent_output_dir: Path,
    prefix: Optional[Union[int, str]],
    constraints: Optional[ExecutionConstraints] = None,
    current_index_path: Optional[List[int]] = None,
    parent_location_code: str = "",
    sequential_counter: Optional[List[int]] = None,
) -> BlockExecutionResult:
    from plinth.block_dag import BlockExecutionResult

    stage = block._get_stage()

    if prefix and isinstance(prefix, str):
        location_code = block._build_location_code(prefix, parent_location_code)
        stage_dir_name = block.get_block_directory_name(prefix, location_code)
    elif parent_location_code:
        branch_counters_key = f"_branch_counters_{parent_location_code}"
        if branch_counters_key not in block.config:
            block.config[branch_counters_key] = [1]
        branch_counter = block.config[branch_counters_key]
        stage_num = branch_counter[0]
        branch_counter[0] += 1
        location_code = parent_location_code + f"{stage_num:02d}"
        stage_dir_name = f"{location_code}_{block.name}"
    else:
        if sequential_counter is None:
            sequential_counter = [1]
        stage_num = sequential_counter[0]
        sequential_counter[0] += 1
        stage_dir_name = f"{stage_num:02d}_{block.name}"

    output_dir = parent_output_dir / stage_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Executing stage: {block.name}")
    logger.info(f"  Input(s): {[str(d) for d in input_dirs]}")
    logger.info(f"  Output: {output_dir}")

    if len(input_dirs) == 1:
        context: FileSystemStageContext | MultiInputStageContext = FileSystemStageContext(
            input_dir=input_dirs[0],
            output_dir=output_dir,
            manifest=None,
        )
    else:
        context = MultiInputStageContext(
            input_dirs=input_dirs,
            output_dir=output_dir,
            manifest=None,
        )

    from plinth.flow.runtime import get_flow_arming_hash
    from plinth.stage_execution_facade import StageExecutionFacade

    arming_hash = get_flow_arming_hash(block.config)
    StageExecutionFacade().run(block.name, stage, context, arming_hash=arming_hash)

    export_flags = block.config.get("export_flags", {})
    if export_flags.get(block.name):
        from plinth.runtime.export_engine import ExportEngine

        experiment_dir = Path(block.config.get("_experiment_dir", parent_output_dir))
        ExportEngine().export_stage_output(
            experiment_dir,
            output_dir,
            block.name,
            stage_dir_name,
        )

    return BlockExecutionResult(
        output_dirs=[output_dir],
        block_name=block.name,
        block_type="stage",
    )
