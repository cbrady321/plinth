# Golden pipeline equivalence

Each tier runs a small hermetic pipeline and compares its final manifest rows, ledger chain, schema and directory layout with committed snapshots, so any change in engine output shows up as a test failure.

## Topology tiers (GT1–GT10)

| Tier | Topology | Config fixture | Snapshots |
|------|----------|----------------|-----------|
| GT1 | Single typical stage (`allowlist_filter`) | `tests/fixtures/golden_pipeline/config.yaml` | `tests/golden/tiers/gt1/` |
| GT2 | Sequential ≥3 stages | `tests/fixtures/golden_pipeline/tiers/gt2/config.yaml` | `tests/golden/tiers/gt2/` |
| GT3 | Parallel join (2 branches → filter) | `tests/fixtures/golden_pipeline/tiers/gt3/config.yaml` | `tests/golden/tiers/gt3/` |
| GT4 | Exceptional stage isolation | `tests/fixtures/golden_pipeline/tiers/gt4/config.yaml` | `tests/golden/tiers/gt4/` |
| GT5 | Mixed: exceptional first, then sequential, parallel without merge, join | `tests/fixtures/golden_pipeline/tiers/gt5/config.yaml` | `tests/golden/tiers/gt5/` |
| GT6 | Deep nested seq→par→seq→stage | `tests/fixtures/golden_pipeline/tiers/gt6/config.yaml` | `tests/golden/tiers/gt6/` |
| GT7 | Expand → aggregate structural chain | `tests/fixtures/golden_pipeline/tiers/gt7/config.yaml` | `tests/golden/tiers/gt7/` |
| GT8 | Resume-from mid-DAG snapshot | `tests/fixtures/golden_pipeline/tiers/gt8/config.yaml` | `tests/golden/tiers/gt8/` |
| GT9 | always_propagate file copy | `tests/fixtures/golden_pipeline/tiers/gt9/config.yaml` | `tests/golden/tiers/gt9/` |
| GT10 | Parallel merge (aggregate_outputs default) | `tests/fixtures/golden_pipeline/tiers/gt10/config.yaml` | `tests/golden/tiers/gt10/` |

The stages the tiers use live in `tests/golden/golden_stages.py`.

## Equivalence rules

- **Manifest:** row dict equality after column sort; the media `path_column` normalized to `<subdir>/<file name>` (`MediaSpec.portable_path`) for portability
- **Ledger:** entry sequence with `input_hash`, `output_hash`, `params_hash`, `files_processed`
- **Schema:** YAML text equality
- **Stage directories:** dir name → sorted relative file names (not content hashes)

## Regenerate snapshots

```bash
python scripts/capture_golden_pipeline.py          # input dataset + GT1
python scripts/capture_golden_tiers.py             # GT2–GT10
```

Re-capture a single tier:

```bash
python -c "
from pathlib import Path
from scripts.capture_golden_tiers import capture_tier, FIXTURE_ROOT
capture_tier('gt2', FIXTURE_ROOT / 'tiers' / 'gt2' / 'config.yaml')
"
```

Commit updated files under `tests/golden/tiers/` only with explicit approval for intentional output changes.

## CI

`pytest tests/golden/` runs equivalence for GT1–GT10 plus hash-chain validation on each tier run.
