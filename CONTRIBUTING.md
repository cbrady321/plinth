# Contributing to plinth

Thanks for your interest. Bug reports, documentation fixes and focused pull requests are all welcome.

## Before you start

- For anything larger than a small fix, open an issue first so we can agree on the approach.
- Plinth stays domain-free: it never imports ML frameworks or application code, and it has no
  registered stages of its own. Features belong in plinth only if any pipeline could use them.
- Every behavioural guarantee is listed in [docs/expectation_matrix.md](docs/expectation_matrix.md)
  with the tests that prove it. A new guarantee needs a row there and a test.

## Development setup

Requires Python 3.11+.

```bash
git clone https://github.com/cbrady321/plinth.git
cd plinth
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
```

## Checks

CI runs all of these on Python 3.11–3.14. Run them before opening a pull request:

```bash
ruff check src/plinth tests/ scripts/ examples/
python scripts/validate_pipeline_configs.py
python scripts/validate_public_surface.py
python scripts/validate_ledger_write_sites.py
python scripts/validate_expectation_matrix.py --check-scenarios
lint-imports
mypy src/plinth tests/typing --follow-imports=silent
pytest tests -q
```

Every script in [`examples/`](examples/README.md) should still run, too.

If you change engine output on purpose, re-capture the golden snapshots and include the reviewed
diff in your pull request:

```bash
python scripts/capture_golden_pipeline.py
python scripts/capture_golden_tiers.py
```

To try the researcher UI against demo runs built from the golden fixtures:

```bash
python scripts/seed_researcher_ui_demo.py
python -m plinth.researcher_ui
```

## Project structure

```
plinth/
├── src/plinth/
│   ├── base_stage.py          # Stage hook surface (process_file, process_group)
│   ├── intent.py              # StageIntent declarations
│   ├── results.py             # StageOutcome return channel
│   ├── registry.py            # Stage registration (empty at init)
│   ├── config.py              # PipelineConfig load/save/validate
│   ├── context.py             # InMemoryStageContext, FileSystemStageContext
│   ├── dag_structures.py      # Typed DAG builders
│   ├── experiment_launcher.py # Validated pipeline entry point
│   ├── dataset/               # Manifest, schema (identity, media spec), ledger structures
│   ├── runtime/               # Executors, propagation, ledger, hash chain
│   ├── address/               # On-disk directory resolution
│   ├── researcher_ui/         # Optional web UI for completed runs
│   ├── testing/               # Hermetic test harness for stage authors
│   └── schemas/               # pipeline_config.schema.json
├── docs/                      # Author and maintainer guides
├── examples/                  # Runnable pipelines: tabular, text, images, audio, video
├── tests/
│   ├── invariants/            # Contract and policy enforcement
│   ├── golden/                # Pipeline equivalence snapshots
│   └── adoption/              # Import boundary and dependency checks
└── scripts/                   # CI checks, golden capture, UI demo seeding
```

[docs/internals.md](docs/internals.md) explains how the engine fits together.

## Pull requests

- Keep each pull request to one change, with tests.
- Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md) for anything a user would notice.
- Changes to the stage author surface also update
  [docs/stage_author_contract.md](docs/stage_author_contract.md).

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE),
and to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
