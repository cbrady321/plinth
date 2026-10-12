"""Hermetic stages used only by golden topology tier fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from plinth.base_stage import BaseStage
from plinth.context import StageContext
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome
from plinth.runtime.hashing import compute_directory_hash, compute_params_hash
from plinth.runtime.ledger_writer import LedgerWriter
from tests.hermetic_stages import HermeticAllowlistFilterStage

StageRegistry.register("golden_filter_b")(HermeticAllowlistFilterStage)


@StageRegistry.register("golden_branch_a")
class GoldenBranchAStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            write_columns={"branch_a": "str"},
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(branch_a="a")


@StageRegistry.register("golden_branch_b")
class GoldenBranchBStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            write_columns={"branch_b": "str"},
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(branch_b="b")


@StageRegistry.register("golden_exceptional", mode="exceptional")
class GoldenExceptionalStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        raise NotImplementedError("golden_exceptional uses execute()")

    def execute(self, context: StageContext) -> Path:
        output_dir = context.get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = context.get_manifest()
        if manifest is not None:
            context.update_manifest(manifest, replace=True)
        schema = context.get_schema()
        context.save_schema(schema)
        ledger = context.get_ledger()
        input_dir = context.get_input_dir()
        LedgerWriter().append_entry(
            ledger,
            stage_name=self.stage_name,
            function_name=self.__class__.__name__,
            input_directory=str(input_dir),
            output_directory=str(output_dir),
            input_hash=compute_directory_hash(input_dir),
            output_hash=compute_directory_hash(output_dir),
            params_hash=compute_params_hash(self.config),
            params=dict(self.config),
            files_processed=len(manifest) if manifest else 0,
            duration_seconds=0.01,
        )
        LedgerWriter().write(ledger, output_dir)
        return output_dir


@StageRegistry.register("golden_join_filter")
class GoldenJoinFilterStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"branch_a", "branch_b"},
            write_columns={},
            filters_rows=True,
            modifies_files=False,
            reads_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        if not metadata.get("branch_a") or not metadata.get("branch_b"):
            return StageOutcome.filter()
        return StageOutcome.update()


@StageRegistry.register("golden_expand_rows")
class GoldenExpandRowsStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            expands_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        base = dict(metadata)
        stem = Path(str(metadata.get("filename") or "row")).stem
        return StageOutcome.expand(
            [
                {**base, "slot": 1, "filename": f"{stem}_c1.bin"},
                {**base, "slot": 2, "filename": f"{stem}_c2.bin"},
            ]
        )


@StageRegistry.register("golden_aggregate_entities")
class GoldenAggregateEntitiesStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            group_by=["entity_id"],
            aggregates_rows=True,
            write_columns={"child_count": "int"},
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        raise NotImplementedError("golden_aggregate_entities uses process_group()")

    def process_group(
        self,
        group_keys: Dict[str, Any],
        rows: List[Dict[str, Any]],
        input_dir: Path,
        output_dir: Path,
    ) -> StageOutcome:
        return StageOutcome.aggregate(
            entity_id=group_keys["entity_id"],
            batch=1,
            slot=None,
            child_count=len(rows),
        )


@StageRegistry.register("golden_noop")
class GoldenNoopStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(noop=True)


@StageRegistry.register("golden_read_touch")
class GoldenReadTouchStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"filename", "file_path"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(touched=True)


@StageRegistry.register("golden_exceptional_structural", mode="exceptional")
class GoldenExceptionalStructuralStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        raise NotImplementedError("golden_exceptional_structural uses execute()")

    def execute(self, context: StageContext) -> Path:
        output_dir = context.get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = context.get_manifest()
        if manifest is not None:
            context.update_manifest(manifest, replace=True)
        schema = context.get_schema()
        context.save_schema(schema)
        summary_path = output_dir / "summary.csv"
        summary_path.write_text("entity_id,value\nitem_a,1.0\nitem_b,2.0\n", encoding="utf-8")
        ledger = context.get_ledger()
        input_dir = context.get_input_dir()
        LedgerWriter().append_entry(
            ledger,
            stage_name=self.stage_name,
            function_name=self.__class__.__name__,
            input_directory=str(input_dir),
            output_directory=str(output_dir),
            input_hash=compute_directory_hash(input_dir),
            output_hash=compute_directory_hash(output_dir),
            params_hash=compute_params_hash(self.config),
            params=dict(self.config),
            files_processed=len(manifest) if manifest else 0,
            duration_seconds=0.01,
        )
        LedgerWriter().write(ledger, output_dir)
        return output_dir


def register_all_golden_stages() -> None:
    from tests.hermetic_stages import register_hermetic_stages

    register_hermetic_stages()
    golden_names = (
        "golden_filter_b",
        "golden_branch_a",
        "golden_branch_b",
        "golden_exceptional",
        "golden_join_filter",
        "golden_expand_rows",
        "golden_aggregate_entities",
        "golden_noop",
        "golden_read_touch",
        "golden_exceptional_structural",
    )
    if not all(name in StageRegistry.list_stages() for name in golden_names):
        import importlib

        import tests.golden.golden_stages as golden_module

        importlib.reload(golden_module)
