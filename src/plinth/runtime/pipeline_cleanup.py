"""Pipeline output directory cleanup helpers."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List

from plinth.address.resolver import NodeAddressResolver
from plinth.blocks import Block
from plinth.jsonpath_resolver import expand_jsonpath_indices, path_to_index_list
from plinth.stage_directory import StageDirectoryManager

logger = logging.getLogger(__name__)


def cleanup_all_stages(stage_manager: StageDirectoryManager) -> None:
    logger.info("🧹 CLEANUP: Starting cleanup of all existing stage directories...")

    stage_manager._parse_existing_directories()
    existing_stages = stage_manager.stage_directories
    existing_blocks = stage_manager.block_directories

    if not existing_stages and not existing_blocks:
        logger.info("🧹 CLEANUP: No existing stage directories to clean up")
        return

    logger.info(
        f"🧹 CLEANUP: Found {len(existing_stages)} stage directories and "
        f"{len(existing_blocks)} block directories to clean up:"
    )
    for stage_dir in existing_stages:
        logger.info(f"🧹 CLEANUP:   - {stage_dir.directory_path}")
    for block_dir in existing_blocks:
        logger.info(f"🧹 CLEANUP:   - {block_dir.directory_path}")

    deleted_count = 0
    for stage_dir in existing_stages:
        if stage_dir.directory_path.exists():
            logger.info(f"🧹 CLEANUP:   Deleting: {stage_dir.directory_path}")
            shutil.rmtree(stage_dir.directory_path)
            deleted_count += 1
        else:
            logger.warning(f"🧹 CLEANUP:   Directory does not exist: {stage_dir.directory_path}")

    for block_dir in existing_blocks:
        if block_dir.directory_path.exists():
            logger.info(f"🧹 CLEANUP:   Deleting: {block_dir.directory_path}")
            shutil.rmtree(block_dir.directory_path)
            deleted_count += 1
        else:
            logger.warning(f"🧹 CLEANUP:   Directory does not exist: {block_dir.directory_path}")

    stage_manager._stage_directories.clear()
    stage_manager._block_directories.clear()
    stage_manager._parse_existing_directories()

    logger.info(f"🧹 CLEANUP: ✓ Successfully deleted {deleted_count} directories")


def cleanup_from_jsonpaths(
    dag_root: Block,
    experiment_dir: Path,
    dag_name: str,
    jsonpaths: List[str],
    address_resolver: NodeAddressResolver,
) -> None:
    logger.info("🧹 CLEANUP: Starting JSONPath-driven cleanup...")

    expanded: List[str] = []
    for path in jsonpaths:
        expanded.extend(expand_jsonpath_indices(path))

    def delete_subtree_at_indices(
        block: Block,
        parent_path: Path,
        prefix: int | str,
        index_path: List[int],
        parent_location_code: str = "",
    ) -> None:
        location_code = NodeAddressResolver.build_location_code(prefix, parent_location_code)
        block_dir_name = block.get_block_directory_name(prefix, location_code)  # type: ignore[attr-defined]
        block_dir = parent_path / block_dir_name

        if not index_path:
            if block_dir.exists():
                logger.info(f"🧹 CLEANUP: Deleting: {block_dir}")
                shutil.rmtree(block_dir)
            return

        child_idx = index_path[0]
        child = block.children[child_idx]
        child_prefix = address_resolver.child_prefix_for_cleanup(block, child, child_idx)
        delete_subtree_at_indices(child, parent_path, child_prefix, index_path[1:], location_code)

    for path in expanded:
        try:
            idx_list = path_to_index_list(path, dag_name)
            delete_subtree_at_indices(dag_root, experiment_dir, 1, idx_list, "")
        except Exception as exc:
            logger.warning(f"🧹 CLEANUP: Failed to clean path {path}: {exc}")


def cleanup_subtree_at_path(
    dag_root: Block,
    experiment_dir: Path,
    index_path: List[int],
    address_resolver: NodeAddressResolver,
) -> None:
    def delete_recursive(
        block: Block,
        parent_path: Path,
        prefix: int | str,
        current_path: List[int],
        parent_location_code: str,
    ) -> None:
        location_code = NodeAddressResolver.build_location_code(prefix, parent_location_code)
        block_dir_name = block.get_block_directory_name(prefix, location_code)  # type: ignore[attr-defined]
        block_dir = parent_path / block_dir_name

        if not current_path:
            if block_dir.exists():
                logger.info(f"🧹 CLEANUP: Deleting {block_dir}")
                shutil.rmtree(block_dir)
            return

        next_idx = current_path[0]
        if next_idx < len(block.children):
            child = block.children[next_idx]
            child_prefix = address_resolver.child_prefix_for_cleanup(block, child, next_idx)
            delete_recursive(child, parent_path, child_prefix, current_path[1:], location_code)

    delete_recursive(dag_root, experiment_dir, 1, index_path, "")
