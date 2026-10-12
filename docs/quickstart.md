# Author quickstart

Get from zero to a passing hermetic stage test in **≤30 minutes** without reading engine source.

**Prerequisites:** Python 3.11+, plinth and pytest installed:

```bash
pip install "plinth @ git+https://github.com/cbrady321/plinth.git@v0.5.0" pytest
```

## Path (four steps)

| Step | Action | Time |
|------|--------|------|
| 1 | Read [Stage author contract](stage_author_contract.md) sections *Typical stage shape* and *StageOutcome* | ~10 min |
| 2 | Skim [Testing recipe](testing_recipe.md) | ~5 min |
| 3 | Copy the recipe into `tests/stages/test_my_stage_typical.py` | ~10 min |
| 4 | Run `pytest tests/stages/test_my_stage_typical.py -q` | ~5 min |

## Minimal worked example

Filter rows by filename — the `AllowlistFilterStage` from README §3:

```python
from plinth.testing import run_typical_stage

from myapp.stages.allowlist_filter import AllowlistFilterStage  # your stage (README §3)


def test_filter_typical_path() -> None:
    stage = AllowlistFilterStage("allowlist_filter", {"allow": ["a.txt"]})
    context = run_typical_stage(
        stage,
        [
            {"entity_id": "s1", "filename": "a.txt"},
            {"entity_id": "s2", "filename": "b.txt"},
        ],
    )
    assert len(context.get_manifest()) == 1
```

Run:

```bash
pytest tests/stages/test_my_stage_typical.py -q
```

Expected: **1 passed**.

## Typical stage checklist

1. Subclass `BaseStage`
2. Implement `get_intent() -> StageIntent`
3. Implement `process_file(...) -> StageOutcome` (or `process_group` when `group_by` is set)
4. Register via `@StageRegistry.register("my_stage")` in your application stage package
5. Do **not** override `execute()` unless the stage is exceptional

## When you need more than typical

See [Choosing a stage kind](stage_kinds.md) before overriding `execute()`.

## Next reads

- [Grouping recipe](recipes/grouping.md) — `group_by` + `StageOutcome.aggregate`
- [Stage author contract §Dataset schema](stage_author_contract.md#dataset-schema-identity-and-file-pointers) — declare your identity keys and file column
- [Testing recipe](testing_recipe.md) — hermetic stage tests without filesystem
