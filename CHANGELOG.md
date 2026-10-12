# Changelog

Package releases follow `__version__` in `src/plinth/version.py`; the stage author contract carries
its own version in the `Version:` header of [stage_author_contract.md](docs/stage_author_contract.md).

## Unreleased

_Nothing yet._

## [0.5.0] — first public release

Author contract 1.0.0. Dataset schema format 1. Python 3.11–3.14.

### Added

- **DAG runtime** — sequential, parallel and nested blocks, defined in YAML (`PipelineConfig`) or with typed builders (`dag_structures`) and checked by `validate_pipeline_config`, which names the offending node for structural mistakes; deterministic on-disk addressing (`NodeAddressResolver`); JSONPath start and end selectors; resume from any stage, rejecting changed upstream parameters; a run-scoped flow-control overlay (`flow_arming`) for switching parallel branches on and off.
- **Stage author surface** — `BaseStage` with `process_file()` / `process_group()` (implement the one your stage uses), a declared `StageIntent`, and typed `StageOutcome` results (update, filter, expand, aggregate); plain dict returns are rejected. Exceptional stages override `execute()` and are checked against runtime obligations.
- **Manifests and schemas** — `DatasetManifest` plus an explicit `dataset_schema.yaml` declaring identity keys (`ManifestIdentity`) and the file-pointer column (`MediaSpec`). Rows may point at files or carry data only; identity is flat unless a hierarchy is declared. The absolute input path the runtime hands each stage (`source_path`) is never written back, so manifests do not depend on where a run lives; a dataset's own `source_path` column is passed through untouched.
- **Ledger and provenance** — an append-only `metadata_ledger.yaml` written only by `LedgerWriter`. Each entry hashes the stage's input and output directories: canonical manifest rows, the schema, and every file keyed by its relative path. Merges of parallel branches are recorded, and the hash chain is validated after every run.
- **Policies** — progress bars only on a terminal (`TQDM_DISABLE=1` turns them off); fail-fast row and parallel-branch failure by default, opt-in partial success with a drop cap, a partial-dataset row-count guard, intent conformance checks, and cleanup that refuses to delete directories it cannot parse. `DataLayout` sets where runs are written.
- **Testing harness** — `plinth.testing` (`InMemoryStageContext`, `TypicalStageExecutor`, `run_typical_stage`) for hermetic stage tests.
- **Researcher UI** (`ui` extra) — browse runs, manifests, schemas, ledgers and failures, and compare runs. Local-only by default: it binds to loopback, checks the `Host` header, and serves files only from inside a run directory.
- **Examples** — runnable, dependency-free pipelines for tabular records, text, images, audio and video, all executed in CI.
- **Verification** — a published pipeline-config JSON Schema, stage parameter schemas, golden topology tiers GT1–GT10, the [expectation matrix](docs/expectation_matrix.md) linking every guarantee to a positive and a negative test, and import-linter contracts.
