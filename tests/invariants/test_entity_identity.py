"""Manifest identity protocol (E53)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from plinth.base_stage import BaseStage
from plinth.context import MultiInputStageContext
from plinth.dataset.identity import ManifestIdentity, apply_column_aliases
from plinth.dataset.manifest_paths import dataset_schema_path, manifest_csv_path
from plinth.dataset.media import NO_SOURCE_FILE, MediaSpec
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.intent import StageIntent
from plinth.results import StageOutcome
from plinth.testing import run_typical_stage


def test_declared_alias_normalizes_to_entity_id() -> None:
    df = pd.DataFrame({"record_id": ["s1"], "batch": [1], "slot": [None], "filename": ["a.bin"]})
    identity = ManifestIdentity(column_aliases={"record_id": "entity_id"})
    manifest = DatasetManifest(df, schema=DatasetSchema(identity=identity))
    assert "entity_id" in manifest.df.columns
    assert manifest.df.iloc[0]["entity_id"] == "s1"
    assert "record_id" not in manifest.df.columns


def test_default_identity_declares_no_aliases() -> None:
    assert ManifestIdentity().column_aliases == {}
    df = pd.DataFrame({"record_id": ["s1"], "batch": [1]})
    assert "record_id" in apply_column_aliases(df, ManifestIdentity()).columns


def test_unknown_alias_column_not_mapped() -> None:
    identity = ManifestIdentity()
    df = pd.DataFrame({"custom_entity": ["s1"], "batch": [1]})
    out = apply_column_aliases(df, identity)
    assert "custom_entity" in out.columns
    assert "entity_id" not in out.columns


# --- flat by default, hierarchy only when declared -------------------------------------------

PAGES = ManifestIdentity(
    entity_key="doc_id",
    hierarchy_keys=["page"],
    key_types={"page": "int"},
    key_defaults={"page": 1},
)


class _ScoreRows(BaseStage):
    seen: list[Any] = []

    def get_intent(self) -> StageIntent:
        return StageIntent(write_columns={"score": "float"}, reads_files=False, modifies_files=False)

    def process_file(self, input_path: Path, output_path: Path, metadata: Any) -> StageOutcome:
        type(self).seen.append(input_path)
        return StageOutcome.update(score=float(metadata["value"]) * 2)


def test_tabular_rows_flow_through_without_injected_columns() -> None:
    _ScoreRows.seen = []
    context = run_typical_stage(_ScoreRows("score", {}), [{"entity_id": "r1", "value": 1}, {"entity_id": "r2", "value": 2}])
    manifest = context.get_manifest()
    assert manifest is not None
    assert sorted(manifest.df.columns) == ["entity_id", "score", "value"]
    assert list(manifest.df["score"]) == [2.0, 4.0]
    assert _ScoreRows.seen == [NO_SOURCE_FILE, NO_SOURCE_FILE]


def test_declared_hierarchy_drives_fill_coercion_and_matching() -> None:
    df = pd.DataFrame({"doc_id": ["d1", "d1", "d2"], "page": [None, 2.0, None], "text": ["a", "b", "c"]})
    manifest = DatasetManifest(df, schema=DatasetSchema(identity=PAGES))
    assert list(manifest.df["page"]) == [1, 2, 1]
    assert manifest.schema.effective_unique_key(set(manifest.df.columns)) == ["doc_id", "page"]
    manifest.update_entry_for_row({"doc_id": "d1", "page": 2}, {"text": "B"})
    assert list(manifest.df["text"]) == ["a", "B", "c"]


def test_int_key_type_requires_a_default() -> None:
    with pytest.raises(ValueError, match="key_defaults"):
        ManifestIdentity(hierarchy_keys=["page"], key_types={"page": "int"})
    with pytest.raises(ValueError, match="unknown kinds"):
        ManifestIdentity(key_types={"page": "float"})


def test_multi_input_merge_keeps_the_declared_identity_and_media(tmp_path: Path) -> None:
    schema = DatasetSchema(identity=PAGES, media=MediaSpec(path_column="text_path", subdir="texts"))
    dirs = []
    for name, value in (("left", "x"), ("right", "y")):
        d = tmp_path / name
        d.mkdir()
        pd.DataFrame({"doc_id": ["d1", "d1"], "page": [1, 2], name: [value, value]}).to_csv(
            manifest_csv_path(d), index=False
        )
        schema.to_yaml(dataset_schema_path(d))
        dirs.append(d)
    context = MultiInputStageContext(dirs, tmp_path / "out")
    assert context.get_schema().identity == PAGES
    assert context.get_schema().media == schema.media
    merged = context.get_manifest()
    assert merged is not None
    assert len(merged) == 2
    assert sorted(merged.df.columns) == ["doc_id", "left", "page", "right"]
