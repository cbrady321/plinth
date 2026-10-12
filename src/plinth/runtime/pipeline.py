"""Pipeline orchestration with automatic path management and ledger tracking."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from plinth.address.resolver import NodeAddressResolver
from plinth.block_dag import BlockExecutionResult, ExecutionConstraints
from plinth.blocks import Block, StageNode
from plinth.config import PipelineConfig
from plinth.context import FileSystemStageContext
from plinth.dataset.structures import MetadataLedger
from plinth.flow.runtime import attach_flow_run_context, build_flow_run_context
from plinth.jsonpath_resolver import expand_jsonpath_indices, path_to_index_list, resolve_index_path
from plinth.layout import DataLayout
from plinth.registry import StageRegistry
from plinth.runtime.pipeline_cleanup import (
    cleanup_all_stages,
    cleanup_from_jsonpaths,
    cleanup_subtree_at_path,
)
from plinth.stage_directory import StageDirectoryManager

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        config: PipelineConfig,
        experiment_name: str,
        project_root: Path,
        layout: Optional[DataLayout] = None,
    ):
        self.config = config
        self.experiment_name = experiment_name
        self.project_root = Path(project_root)
        self.layout = layout or DataLayout()
        self.data_root = self.layout.data_root(self.project_root)
        self.dataset_dir = self.layout.input_dir(self.project_root)
        self.experiment_dir = self.layout.run_dir(self.project_root, experiment_name)
        self.stage_manager = StageDirectoryManager(self.experiment_dir)
        self._address_resolver = NodeAddressResolver()
        self._dag_root: Block
        self._load_stages()

    def get_stage_names(self) -> List[str]:
        return self._dag_root.get_all_stage_names()

    def _load_stages(self) -> None:
        if not self.config.dag:
            raise ValueError("PipelineConfig.dag must be provided")
        self._dag_root = self.config.build_dag()
        logger.debug(f"Loaded DAG root: {self._dag_root.name}")

    def _resume_stage_name_from_index_path(self, index_path: List[int]) -> str:
        node = resolve_index_path(self._dag_root, index_path)
        if isinstance(node, StageNode):
            return node.name
        names = node.get_all_stage_names()
        if not names:
            raise ValueError(f"No stages under JSONPath index path {index_path}")
        return names[0]

    def run(
        self,
        input_source: Optional[str] = None,
        stage_filter: Optional[List[str]] = None,
        start_from_stage: Optional[str] = None,
        end_at_stage: Optional[str] = None,
    ) -> Path:
        effective_start_stage = start_from_stage
        effective_end_stage = end_at_stage

        start_index_paths: List[List[int]] = []
        config_start_paths = self.config.start_from_paths or []
        jsonpaths_to_clean: List[str] = []
        root_name = self.config.dag["name"] if self.config.dag else "root"

        for path in config_start_paths:
            if path.startswith("$"):
                jsonpaths_to_clean.append(path)
                expanded = expand_jsonpath_indices(path)
                for expanded_path in expanded:
                    start_index_paths.append(path_to_index_list(expanded_path, root_name))
            else:
                idx_path = self._dag_root.find_path_to_stage(path)
                if not idx_path:
                    raise ValueError(f"Stage '{path}' not found in DAG")
                start_index_paths.append(idx_path)

        if effective_start_stage:
            idx_path = self._dag_root.find_path_to_stage(effective_start_stage)
            if not idx_path:
                raise ValueError(f"Stage '{effective_start_stage}' not found in DAG")
            start_index_paths = [idx_path]

        end_index_paths: List[List[int]] = []
        config_end_paths = self.config.end_at_paths or []

        for path in config_end_paths:
            if path.startswith("$"):
                expanded_end = expand_jsonpath_indices(path)
                for expanded_path in expanded_end:
                    end_index_paths.append(path_to_index_list(expanded_path, root_name))
            else:
                idx_path = self._dag_root.find_path_to_stage(path)
                if not idx_path:
                    raise ValueError(f"Stage '{path}' not found in DAG")
                end_index_paths.append(idx_path)

        if effective_end_stage:
            end_path = self._dag_root.find_path_to_stage(effective_end_stage)
            if end_path:
                end_index_paths.append(end_path)

        for idx_path in start_index_paths + end_index_paths:
            resolve_index_path(self._dag_root, idx_path)

        if start_index_paths:
            from plinth.flow.resume import validate_arming_on_resume
            from plinth.flow.runtime import flow_arming_is_active
            from plinth.runtime.resume_policy import validate_upstream_params_on_resume

            resume_stage_name = self._resume_stage_name_from_index_path(min(start_index_paths))
            validate_upstream_params_on_resume(
                self.experiment_dir,
                self._dag_root,
                resume_stage_name,
                self.config.params,
                self.config.always_propagate,
            )
            if flow_arming_is_active(self.config.flow_arming):
                flow_context = build_flow_run_context(
                    self.config,
                    self.experiment_name,
                    self._dag_root,
                )
                if flow_context is not None:
                    validate_arming_on_resume(
                        self.experiment_dir,
                        self._dag_root,
                        resume_stage_name,
                        flow_context.run_identity,
                    )

        if start_index_paths:
            logger.info(f"🚀 Starting pipeline from: {start_index_paths}")
            for idx_path in start_index_paths:
                cleanup_subtree_at_path(
                    self._dag_root,
                    self.experiment_dir,
                    idx_path,
                    self._address_resolver,
                )
        elif jsonpaths_to_clean:
            logger.info(f"🚀 Starting pipeline from JSONPaths: {jsonpaths_to_clean}")
            cleanup_from_jsonpaths(
                self._dag_root,
                self.experiment_dir,
                root_name,
                jsonpaths_to_clean,
                self._address_resolver,
            )
        else:
            logger.info("🚀 Running full pipeline - cleaning up all existing stage directories")
            cleanup_all_stages(self.stage_manager)

        if input_source:
            current_input_dir = Path(input_source)
        elif self.config.input_source:
            current_input_dir = self.data_root / Path(self.config.input_source)
        else:
            current_input_dir = self.dataset_dir

        if not current_input_dir.exists():
            raise ValueError(f"Input directory does not exist: {current_input_dir}")

        logger.info(f"\n{'=' * 80}")
        logger.info(f"Starting pipeline '{self.config.name}' experiment '{self.experiment_name}'")
        logger.info(f"Version: {self.config.version}")
        logger.info(f"Input: {current_input_dir}")
        logger.info(f"{'=' * 80}\n")

        parent_output_dir = self.experiment_dir
        initial_inputs = [current_input_dir]
        constraints: Optional[ExecutionConstraints] = None

        start_constraint_path = None
        if start_index_paths:
            start_constraint_path = min(start_index_paths)

        if start_constraint_path or end_index_paths:
            constraints = ExecutionConstraints(
                end_index_paths=end_index_paths,
                start_index_path=start_constraint_path,
            )

        self._dag_root.config["_experiment_dir"] = str(self.experiment_dir)
        attach_flow_run_context(
            self._dag_root,
            build_flow_run_context(self.config, self.experiment_name, self._dag_root),
        )

        sequential_counter = [1]

        result: BlockExecutionResult = self._dag_root.execute(
            initial_inputs,
            parent_output_dir,
            1,
            constraints=constraints,
            current_index_path=None,
            parent_location_code="",
            sequential_counter=sequential_counter,
        )
        output_dirs = result.output_dirs

        logger.info(f"\n{'=' * 80}")
        logger.info("✓ Pipeline completed successfully!")
        logger.info(f"  Final outputs: {output_dirs}")

        final_ledger = MetadataLedger.from_directory(output_dirs[0]) if output_dirs else MetadataLedger()
        from plinth.runtime.hash_chain_validator import validate_hash_chain

        validate_hash_chain(final_ledger)
        logger.info(f"  Pipeline version: {final_ledger.get_pipeline_version()}")
        logger.info(f"  Stage history: {' → '.join(final_ledger.get_stage_history())}")
        logger.info(f"{'=' * 80}\n")

        return output_dirs[0] if output_dirs else current_input_dir

    def cleanup_from_jsonpaths(self, jsonpaths: List[str]) -> None:
        root_name = self.config.dag["name"] if self.config.dag else "root"
        cleanup_from_jsonpaths(
            self._dag_root,
            self.experiment_dir,
            root_name,
            jsonpaths,
            self._address_resolver,
        )

    def _cleanup_subtree_at_path(self, index_path: List[int]) -> None:
        cleanup_subtree_at_path(
            self._dag_root,
            self.experiment_dir,
            index_path,
            self._address_resolver,
        )

    def run_isolated_stage(
        self,
        stage_name: str,
        input_source: Optional[str] = None,
        output_suffix: str = "",
    ) -> Path:
        available = self.get_stage_names()
        if stage_name not in available:
            raise ValueError(f"Stage '{stage_name}' not found. Available: {available}")

        stage_class = StageRegistry.get_stage(stage_name)
        stage_params = dict(self.config.params.get(stage_name, {}))
        if self.config.always_propagate:
            stage_params["_always_propagate"] = True
        stage = stage_class(stage_name=stage_name, config=stage_params)

        current_input_dir = Path(input_source) if input_source else self.dataset_dir
        if not current_input_dir.exists():
            raise ValueError(f"Input directory does not exist: {current_input_dir}")

        if output_suffix:
            stage_output_dir = self.experiment_dir / f"{stage_name}{output_suffix}"
        else:
            stage_output_dir = self.stage_manager.get_output_directory_for_stage(stage_name)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Running isolated stage: {stage_name}")
        logger.info(f"  Input:  {current_input_dir}")
        logger.info(f"  Output: {stage_output_dir}")
        logger.info(f"{'=' * 60}\n")

        context = FileSystemStageContext(
            input_dir=current_input_dir,
            output_dir=stage_output_dir,
            manifest=None,
        )
        stage.execute(context)

        logger.info(f"\n✓ Isolated stage completed: {stage_output_dir}\n")
        return stage_output_dir

    def _export_stage_output(self, stage_output_dir: Path) -> None:
        from plinth.runtime.export_engine import ExportEngine

        ExportEngine().export_stage_output(
            self.experiment_dir,
            stage_output_dir,
            stage_output_dir.name,
            stage_output_dir.name,
        )
