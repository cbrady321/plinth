"""Base stage class — domain hook surface; lifecycle owned by the runtime."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, cast

from plinth.context import FileSystemStageContext, StageContext
from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.rows import CoreManifestRow
from plinth.runtime.hashing import compute_directory_hash, compute_params_hash
from plinth.runtime.manifest_policy import should_replace_manifest
from plinth.runtime.stage_processor import StageFileProcessor

logger = logging.getLogger(__name__)


class BaseStage:
    def __init__(self, stage_name: str, config: Dict[str, Any]) -> None:
        self.stage_name = stage_name
        self.config = config
        self._start_time: Optional[float] = None
        self._files_processed: int = 0
        self._dropped_rows: int = 0
        self._context: Optional[StageContext] = None

    def get_intent(self) -> StageIntent:
        return StageIntent()

    def prepare_context(self, context: StageContext) -> None:
        return None

    def finalize_output(self, context: StageContext, output_dir: Path) -> Path:
        return output_dir

    def execute(self, context: StageContext) -> Path:
        from plinth.runtime.executor import TypicalStageExecutor

        return cast(Path, TypicalStageExecutor().run(self, context))

    def execute_with_paths(
        self,
        input_dir: Path,
        output_dir: Path,
        manifest: Optional[DatasetManifest] = None,
    ) -> Path:
        context = FileSystemStageContext(input_dir, output_dir, manifest)
        return self.execute(context)

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        metadata: CoreManifestRow,
    ) -> StageOutcome:
        """Per-row hook for typical stages without ``group_by``."""
        raise TypeError(
            f"Stage '{self.stage_name}' must implement process_file() (or set group_by and implement process_group())"
        )

    def process_group(
        self,
        group_keys: CoreManifestRow,
        rows: list[CoreManifestRow],
        input_dir: Path,
        output_dir: Path,
    ) -> StageOutcome:
        """Per-group hook for typical stages whose intent sets ``group_by``."""
        raise TypeError(f"Stage '{self.stage_name}' sets group_by and must implement process_group()")

    def _get_stage_input_dir(self, input_path: Path) -> Path:
        if self._context is not None:
            return cast(Path, self._context.get_input_dir())
        return input_path.parent.parent

    def _get_stage_output_dir(self, output_path: Path) -> Path:
        if self._context is not None:
            return cast(Path, self._context.get_output_dir())
        return output_path.parent.parent

    def _should_replace_manifest(self, intent: StageIntent) -> bool:
        return cast(bool, should_replace_manifest(intent))

    def _process_all_files(
        self,
        input_dir: Path,
        output_dir: Path,
        manifest: Optional[DatasetManifest],
    ) -> None:
        StageFileProcessor().process(self, input_dir, output_dir, manifest)

    def _compute_directory_hash(self, directory: Path) -> str:
        return cast(str, compute_directory_hash(directory))

    def _compute_params_hash(self) -> str:
        return cast(str, compute_params_hash(self.config))
