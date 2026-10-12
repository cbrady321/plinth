"""Output/intent conformance checks for typical stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from plinth.dataset.structures import DatasetManifest
from plinth.intent import StageIntent
from plinth.registry import StageRegistry


def verify_output_intent_conformance(
    stage: Any,
    intent: StageIntent,
    input_manifest: Optional[DatasetManifest],
    output_manifest: Optional[DatasetManifest],
    output_dir: Path,
) -> None:
    stage_name = stage.stage_name

    if output_manifest and intent.write_columns and len(output_manifest) > 0:
        missing = set(intent.write_columns.keys()) - set(output_manifest.df.columns)
        if missing:
            raise ValueError(f"Stage {stage_name} declared output columns {missing} but manifest does not contain them")

    if (
        input_manifest is not None
        and output_manifest is not None
        and intent.filters_rows
        and len(input_manifest) > 0
        and len(output_manifest) > len(input_manifest)
    ):
        raise ValueError(
            f"Stage {stage_name} declares filters_rows=True but output row count "
            f"{len(output_manifest)} exceeds input {len(input_manifest)}"
        )

    metadata = StageRegistry.get_exceptional_metadata(stage_name)
    if metadata:
        for sidecar in metadata.sidecar_artifacts:
            sidecar_path = output_dir / sidecar.filename
            if not sidecar_path.exists():
                raise ValueError(
                    f"Stage {stage_name} declared auxiliary artifact {sidecar.filename!r} missing at {sidecar_path}"
                )
