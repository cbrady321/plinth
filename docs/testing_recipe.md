# Hermetic stage testing recipe

Authoritative guide for testing typical stage domain logic without a filesystem tree.

## When to use

- Domain transformation logic (filter, map columns, expand rows)
- Intent validation in unit tests
- CI jobs that must not depend on `data/` or network

Use golden pipeline tests (`tests/golden/`) for full DAG equivalence. Use this recipe for single-stage logic.

## Recipe

```python
import pandas as pd

from plinth.dataset.structures import DatasetManifest
from plinth.rows import CoreManifestRow
from plinth.results import StageOutcome
from plinth.testing import InMemoryStageContext, TypicalStageExecutor
from myapp.stages.allowlist_filter import AllowlistFilterStage  # your stage (README §3)


def test_my_stage_filters_rows() -> None:
    manifest = DatasetManifest(
        pd.DataFrame(
            {
                "entity_id": ["s1", "s2"],
                "filename": ["a.txt", "b.txt"],
                "file_path": ["files/a.txt", "files/b.txt"],
            }
        )
    )
    context = InMemoryStageContext(manifest=manifest)
    stage = AllowlistFilterStage("allowlist_filter", {"allow": ["a.txt"]})
    TypicalStageExecutor().run(stage, context)
    result = context.get_manifest()
    assert result is not None
    assert len(result) == 1


def test_typed_metadata_signature() -> None:
    from plinth.base_stage import BaseStage

    class TagStage(BaseStage):
        def process_file(self, input_path, output_path, metadata: CoreManifestRow) -> StageOutcome:
            return StageOutcome.update(tag=metadata.get("entity_id", ""))
```

Rows are flat by default (`DatasetSchema()`: `entity_id` only, file column `file_path`). If your
dataset has a hierarchy or a different file column, pass your schema:
`minimal_manifest(rows, schema=my_schema)` / `run_typical_stage(stage, rows, schema=my_schema)`.

## Steps

1. Build a `DatasetManifest` DataFrame with your identity columns (pass your `DatasetSchema` when it is not the default).
2. Construct `InMemoryStageContext(manifest=...)`.
3. Instantiate the stage with name + params dict (same shape as YAML `params.<stage>`).
4. Call `TypicalStageExecutor().run(stage, context)`.
5. Assert on `context.get_manifest()` and optional schema via `context.get_schema()`.

## Exceptional stages

Exceptional stages override `execute()`. Test with `FileSystemStageContext` in `tmp_path` or mock context methods. Runtime obligations are verified by `tests/invariants/test_exceptional_runtime_obligations.py`.

## CI example

`tests/invariants/test_recipe_demo.py` runs this recipe in CI. Keep it green when changing the harness or reference stage.

## References

- Author contract: [stage_author_contract.md](stage_author_contract.md)
- Golden tiers: `tests/golden/README.md`
- Guarantees and their tests: [expectation_matrix.md](expectation_matrix.md)
