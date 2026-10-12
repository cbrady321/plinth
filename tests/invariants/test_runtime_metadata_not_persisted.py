"""The runtime-set ``source_path`` on ``process_file`` metadata never leaks into persisted manifests,
and never overwrites a dataset's own ``source_path`` column."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from plinth.dataset.media import SOURCE_PATH_KEY
from plinth.dataset.structures import DatasetManifest
from plinth.results import StageOutcome
from plinth.runtime.outcome_handler import OutcomeHandler
from tests.golden.run_harness import experiment_dir, prepare_work_dir, run_pipeline

INJECTED = frozenset({SOURCE_PATH_KEY})


def test_expanded_rows_drop_injected_key() -> None:
    new_rows: list[dict] = []
    metadata = {"entity_id": "a", SOURCE_PATH_KEY: "/abs/a.bin"}
    OutcomeHandler("s", runtime_keys=INJECTED).handle_result(
        StageOutcome.expand([{**metadata, "slot": 1}, {**metadata, "slot": 2}]),
        {"entity_id": "a"},
        new_rows,
        True,
    )
    assert new_rows == [{"entity_id": "a", "slot": 1}, {"entity_id": "a", "slot": 2}]


def test_structural_updates_drop_injected_key() -> None:
    new_rows: list[dict] = []
    OutcomeHandler("s", runtime_keys=INJECTED).handle_result(
        StageOutcome.update(**{SOURCE_PATH_KEY: "/abs/a.bin", "score": 1}), {"entity_id": "a"}, new_rows, True
    )
    assert new_rows == [{"entity_id": "a", "score": 1}]


def test_in_place_updates_drop_injected_key() -> None:
    manifest = DatasetManifest(pd.DataFrame([{"entity_id": "a"}]))
    OutcomeHandler("s", runtime_keys=INJECTED).handle_result(
        StageOutcome.update(**{SOURCE_PATH_KEY: "/abs/a.bin", "score": 1}),
        {"entity_id": "a"},
        None,
        False,
        manifest,
        row_index=0,
    )
    assert SOURCE_PATH_KEY not in manifest.df.columns
    assert manifest.df.loc[0, "score"] == 1


def test_input_column_of_the_same_name_is_kept() -> None:
    new_rows: list[dict] = []
    OutcomeHandler("s", runtime_keys=frozenset()).handle_result(
        StageOutcome.expand([{"entity_id": "a", SOURCE_PATH_KEY: "upstream/a.bin"}]), {"entity_id": "a"}, new_rows, True
    )
    assert new_rows == [{"entity_id": "a", SOURCE_PATH_KEY: "upstream/a.bin"}]


def test_expanding_pipeline_manifests_carry_no_source_path(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt7")
    run_pipeline("gt7", work)
    manifests = list(experiment_dir(work, "gt7").rglob("manifest.csv"))
    assert manifests
    for manifest_path in manifests:
        assert SOURCE_PATH_KEY not in pd.read_csv(manifest_path).columns, manifest_path


def test_dataset_source_path_column_is_passed_through_untouched(tmp_path: Path) -> None:
    work = prepare_work_dir(tmp_path, "gt7")
    dataset_manifest = work / "data" / "dataset" / "manifest.csv"
    df = pd.read_csv(dataset_manifest)
    df[SOURCE_PATH_KEY] = [f"origin/{name}" for name in df["filename"]]
    df.to_csv(dataset_manifest, index=False)
    own_values = dict(zip(df["entity_id"], df[SOURCE_PATH_KEY]))

    run_pipeline("gt7", work)

    checked = 0
    for manifest_path in experiment_dir(work, "gt7").rglob("manifest.csv"):
        stage_df = pd.read_csv(manifest_path)
        if SOURCE_PATH_KEY not in stage_df.columns:
            continue  # aggregation keeps only the columns it returns
        for entity_id, value in zip(stage_df["entity_id"], stage_df[SOURCE_PATH_KEY]):
            assert value == own_values[entity_id], manifest_path
            checked += 1
    assert checked  # the filter and expand stages both carried the column
