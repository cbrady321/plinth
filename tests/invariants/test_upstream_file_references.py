"""Relative file references survive metadata-only stages.

Stages with ``modifies_files=False`` pass ``<path_column>`` values through without copying files, so
a relative value must keep resolving downstream: first against the stage input directory, then
against the upstream directories recorded in the ledger (nearest first).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.context import FileSystemStageContext
from plinth.dataset.manifest_paths import manifest_csv_path
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetManifest, MetadataLedger, MetadataLedgerEntry
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome
from plinth.runtime.pipeline import Pipeline


class _TagStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(write_columns={"tag": "str"}, reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(tag="seen")


class _ReadStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(write_columns={"content": "str"}, reads_files=True, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(content=input_path.read_text())


class _RewriteStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(reads_files=True, modifies_files=True)

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        output_path.write_text(input_path.read_text().upper())
        return StageOutcome.update()


def _dataset(root: Path) -> Path:
    (root / "files").mkdir(parents=True)
    (root / "files" / "a.txt").write_text("alpha")
    (root / "files" / "b.txt").write_text("beta")
    pd.DataFrame({"entity_id": ["a", "b"], "file_path": ["files/a.txt", "files/b.txt"]}).to_csv(
        manifest_csv_path(root), index=False
    )
    return root


def _run(tmp_path: Path, stages: list[str]) -> DatasetManifest:
    config = PipelineConfig(
        name="upstream_refs",
        version="1.0",
        dag={"type": "sequential", "name": "root", "children": [{"type": "stage", "name": s} for s in stages]},
    )
    output = Pipeline(config, "upstream_refs", tmp_path).run(input_source=str(_dataset(tmp_path / "dataset")))
    return DatasetManifest.from_csv(manifest_csv_path(Path(output)))


@pytest.fixture
def stages(isolated_registry: None) -> None:
    StageRegistry.register("tag_a")(_TagStage)
    StageRegistry.register("tag_b")(_TagStage)
    StageRegistry.register("read")(_ReadStage)
    StageRegistry.register("rewrite")(_RewriteStage)


@pytest.mark.usefixtures("stages")
def test_file_reader_after_metadata_stages_resolves_original_files(tmp_path: Path) -> None:
    manifest = _run(tmp_path, ["tag_a", "tag_b", "read"])
    assert manifest.df["content"].tolist() == ["alpha", "beta"]
    dataset_files = tmp_path / "dataset" / "files"
    assert [Path(p) for p in manifest.df["file_path"]] == [dataset_files / "a.txt", dataset_files / "b.txt"]


@pytest.mark.usefixtures("stages")
def test_nearest_rewritten_file_wins_over_older_upstream_copy(tmp_path: Path) -> None:
    manifest = _run(tmp_path, ["rewrite", "tag_a", "read"])
    assert manifest.df["content"].tolist() == ["ALPHA", "BETA"]


def test_source_path_prefers_base_dir_then_upstream_in_order(tmp_path: Path) -> None:
    base, near, far = (tmp_path / n for n in ("base", "near", "far"))
    for directory in (near, far):
        (directory / "files").mkdir(parents=True)
        (directory / "files" / "x.bin").write_bytes(directory.name.encode())
    media = MediaSpec()
    row = {"file_path": "files/x.bin"}
    assert media.source_path(row, base, [near, far]) == near / "files" / "x.bin"
    assert media.source_path(row, base, [far]) == far / "files" / "x.bin"
    assert media.source_path(row, base, []) == base / "files" / "x.bin"  # unresolved: anchored at base


def test_source_path_never_escapes_an_upstream_directory(tmp_path: Path) -> None:
    (tmp_path / "secret.bin").write_bytes(b"x")
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    resolved = MediaSpec().source_path({"file_path": "../secret.bin"}, tmp_path / "base", [upstream])
    assert resolved == tmp_path / "base" / ".." / "secret.bin"  # not resolved through upstream


def test_context_input_path_accepts_upstream_files_only(tmp_path: Path) -> None:
    upstream = _dataset(tmp_path / "dataset")
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    ledger = MetadataLedger()
    ledger.append(
        MetadataLedgerEntry(
            stage_name="tag",
            timestamp="t",
            function_name="tag",
            input_directory=str(upstream),
            output_directory=str(stage_dir),
            input_hash="",
            output_hash="",
            params_hash="",
            params={},
            files_processed=2,
            duration_seconds=0.0,
        )
    )
    ledger.to_yaml(stage_dir / "metadata_ledger.yaml")
    pd.read_csv(manifest_csv_path(upstream)).to_csv(manifest_csv_path(stage_dir), index=False)

    context = FileSystemStageContext(stage_dir, tmp_path / "out")
    assert context.get_input_path(entity_id="a") == upstream / "files" / "a.txt"


def test_upstream_directories_are_most_recent_first_and_unique() -> None:
    def entry(src: str) -> MetadataLedgerEntry:
        return MetadataLedgerEntry("s", "t", "f", src, "", "", "", "", {}, 0, 0.0)

    ledger = MetadataLedger(entries=[entry("/d0"), entry("/d1"), entry("/d0"), entry("")])
    assert ledger.upstream_directories() == [Path("/d0"), Path("/d1")]
