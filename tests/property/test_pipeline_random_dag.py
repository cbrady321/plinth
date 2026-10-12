"""Full pipeline execution on sequential noop chains."""

from __future__ import annotations

from pathlib import Path

import pytest

from plinth.config import PipelineConfig
from plinth.dataset.structures import MetadataLedger
from plinth.runtime.hash_chain_validator import validate_hash_chain
from plinth.runtime.pipeline import Pipeline
from tests.golden.run_harness import prepare_work_dir, register_golden_stages


@pytest.mark.property
@pytest.mark.parametrize("extra_noops", [1, 2, 3])
def test_sequential_filter_then_noop_chain_validates(tmp_path: Path, extra_noops: int) -> None:
    work = prepare_work_dir(tmp_path, "gt2")
    children = [{"type": "stage", "name": "allowlist_filter"}]
    children += [{"type": "stage", "name": "golden_noop"}] * extra_noops
    register_golden_stages()
    config = PipelineConfig(
        name="noop_chain",
        version="1",
        input_source="dataset",
        dag={"type": "sequential", "name": "noop_root", "children": children},
        params={
            "allowlist_filter": {"allow": ["a.bin", "b.bin"]},
            "golden_noop": {},
        },
    )
    pipeline = Pipeline(config, "noop_exp", work)
    out = pipeline.run(input_source=str(work / "data" / "dataset"))
    ledger = MetadataLedger.from_yaml(Path(out) / "metadata_ledger.yaml")
    validate_hash_chain(ledger)
    assert len(ledger.entries) == extra_noops + 1
