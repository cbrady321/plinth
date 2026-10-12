"""CI recipe demo for typical stage authoring."""

from __future__ import annotations

import pandas as pd

from plinth.context import InMemoryStageContext
from plinth.dataset.structures import DatasetManifest
from plinth.runtime.executor import TypicalStageExecutor
from tests.hermetic_stages import HermeticAllowlistFilterStage


def test_allowlist_filter_zero_fs_recipe() -> None:
    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1", "s2"],
                "filename": ["a.bin", "b.bin"],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)
    stage = HermeticAllowlistFilterStage(
        "allowlist_filter",
        {"allow": ["a.bin"]},
    )
    TypicalStageExecutor().run(stage, context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 1
    assert result.df.iloc[0]["filename"] == "a.bin"
