"""Hermetic stage implementations for Plinth tests (no domain dependencies)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from plinth.base_stage import BaseStage
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome


def _allowed_names(value: Any) -> frozenset[str]:
    names = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    return frozenset(str(name) for name in names if name is not None and str(name) != "")


@StageRegistry.register("allowlist_filter")
class HermeticAllowlistFilterStage(BaseStage):
    """Keep rows whose ``filename`` is in the ``allow`` list; an empty list keeps every row."""

    def __init__(self, stage_name: str, config: Dict[str, Any]) -> None:
        super().__init__(stage_name, config)
        self.case_insensitive = bool(config.get("case_insensitive", False))
        allowed = _allowed_names(config.get("allow", []))
        self.allowed = frozenset(name.lower() for name in allowed) if self.case_insensitive else allowed

    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"filename"},
            write_columns={},
            filters_rows=True,
            modifies_files=False,
            reads_files=False,
            replaces_manifest=False,
        )

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        metadata: Dict[str, Any],
    ) -> StageOutcome:
        if not self.allowed:
            return StageOutcome.update()
        name = str(metadata.get("filename") or "")
        if self.case_insensitive:
            name = name.lower()
        return StageOutcome.update() if name in self.allowed else StageOutcome.filter()


@StageRegistry.register("tag_category")
class HermeticTagCategoryStage(BaseStage):
    """Copy each row's file into the stage output and set ``category`` (kept when already present)."""

    def __init__(self, stage_name: str, config: Dict[str, Any]) -> None:
        super().__init__(stage_name, config)
        self.default_category = str(config.get("default_category", "none"))

    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"file_path"},
            write_columns={"category": "str", "file_path": "str"},
            modifies_files=True,
            reads_files=False,
            replaces_manifest=False,
            modify_columns={"category", "file_path"},
        )

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        metadata: Dict[str, Any],
    ) -> StageOutcome:
        file_path = str(metadata.get("file_path") or "")
        if not file_path:
            raise ValueError("tag_category requires file_path")

        stage_output_dir = self._get_stage_output_dir(output_path)
        dest_rel = Path("files") / Path(file_path).name
        (stage_output_dir / dest_rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, stage_output_dir / dest_rel)

        current = metadata.get("category")
        category = str(current) if current not in (None, "") and str(current) != "nan" else self.default_category
        return StageOutcome.update(category=category, file_path=str(dest_rel))


def register_hermetic_stages() -> None:
    if "allowlist_filter" not in StageRegistry.list_stages():
        StageRegistry.register("allowlist_filter")(HermeticAllowlistFilterStage)
    if "tag_category" not in StageRegistry.list_stages():
        StageRegistry.register("tag_category")(HermeticTagCategoryStage)
