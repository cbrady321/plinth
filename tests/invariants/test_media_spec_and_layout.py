"""MediaSpec (file-pointer column), DataLayout and consumer-owned param schemas."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.context import FileSystemStageContext
from plinth.dataset.manifest_paths import dataset_schema_path, manifest_csv_path
from plinth.dataset.manifest_rows import normalize_manifest_rows
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.intent import StageIntent
from plinth.layout import DataLayout
from plinth.results import StageOutcome
from plinth.runtime.executor import TypicalStageExecutor
from plinth.runtime.pipeline import Pipeline

IMAGES = MediaSpec(path_column="image_path", subdir="images")


def _image_dataset(root: Path, schema: DatasetSchema) -> Path:
    (root / "images").mkdir(parents=True)
    (root / "images" / "x.png").write_bytes(b"png-bytes")
    schema.to_yaml(dataset_schema_path(root))
    pd.DataFrame(
        {
            "entity_id": ["e1"],
            "batch": [1],
            "slot": [None],
            "filename": ["x.png"],
            "image_path": ["images/x.png"],
        }
    ).to_csv(manifest_csv_path(root), index=False)
    return root


class _CopyStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(write_columns={"size": "int"}, reads_files=True, modifies_files=True)

    def process_file(self, input_path: Path, output_path: Path, metadata: dict[str, Any]) -> StageOutcome:
        shutil.copy2(input_path, output_path)
        return StageOutcome.update(size=input_path.stat().st_size)


def test_default_media_spec_is_written_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "schema.yaml"
    DatasetSchema().to_yaml(path)
    assert "media:" in path.read_text()
    assert DatasetSchema.from_yaml(path).media == MediaSpec()


def test_custom_media_spec_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "schema.yaml"
    DatasetSchema(media=IMAGES).to_yaml(path)
    assert DatasetSchema.from_yaml(path).media == IMAGES


def test_typical_stage_uses_declared_media_column_and_subdir(tmp_path: Path) -> None:
    src = _image_dataset(tmp_path / "in", DatasetSchema(media=IMAGES))
    out = tmp_path / "out"
    context = FileSystemStageContext(src, out)
    TypicalStageExecutor().run(_CopyStage("copy", {}), context)

    assert (out / "images" / "x.png").read_bytes() == b"png-bytes"
    assert not (out / "files").exists()
    manifest = DatasetManifest.from_csv(manifest_csv_path(out))
    assert list(manifest.df["size"]) == [9]


def test_context_resolves_input_path_through_media_column(tmp_path: Path) -> None:
    src = _image_dataset(tmp_path / "in", DatasetSchema(media=IMAGES))
    context = FileSystemStageContext(src, tmp_path / "out")
    assert context.get_input_path(entity_id="e1") == src / "images" / "x.png"


def test_missing_media_column_error_names_the_declared_column(tmp_path: Path) -> None:
    src = _image_dataset(tmp_path / "in", DatasetSchema())  # default spec expects file_path
    context = FileSystemStageContext(src, tmp_path / "out")
    try:
        context.get_input_path(entity_id="e1")
    except ValueError as exc:
        assert "file_path" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_resume_normalization_follows_the_schema_media_spec(tmp_path: Path) -> None:
    src = _image_dataset(tmp_path / "in", DatasetSchema(media=IMAGES))
    pd.read_csv(manifest_csv_path(src)).assign(image_path="/abs/elsewhere/x.png").to_csv(
        manifest_csv_path(src), index=False
    )
    (row,) = normalize_manifest_rows(manifest_csv_path(src))
    assert row["image_path"] == "images/x.png"


def test_pipeline_honours_custom_layout(tmp_path: Path) -> None:
    config = PipelineConfig(
        name="p",
        version="1",
        dag={"type": "sequential", "name": "root", "children": [{"type": "stage", "name": "allowlist_filter"}]},
        params={},
    )
    layout = DataLayout(data_dir="d", runs_dir="d/out/runs", default_input_dir="d/in")
    pipeline = Pipeline(config, "exp", tmp_path, layout=layout)
    assert pipeline.experiment_dir == tmp_path / "d/out/runs/exp"
    assert pipeline.dataset_dir == tmp_path / "d/in"
    assert pipeline.data_root == tmp_path / "d"

    default = Pipeline(config, "exp", tmp_path)
    assert default.experiment_dir == tmp_path / "data/pipeline/runs/exp"


def test_registered_param_schema_violations_are_reported() -> None:
    from tests.hermetic_param_schemas import register_hermetic_param_schemas
    from tests.hermetic_stages import register_hermetic_stages

    register_hermetic_stages()
    register_hermetic_param_schemas()
    config = PipelineConfig(
        name="bad_params",
        version="1",
        dag={"type": "sequential", "name": "root", "children": [{"type": "stage", "name": "allowlist_filter"}]},
        params={"allowlist_filter": {"case_insensitive": "yes"}},
    )
    result = config.validate()
    assert not result.ok
    assert any(e.startswith("stages[0].params.case_insensitive:") for e in result.errors), result.errors
