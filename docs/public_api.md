# Public API and import rules

What your application may import from `plinth`, how stable each part is, and what `plinth` itself
promises never to import.

## Install

```bash
pip install "plinth @ git+https://github.com/cbrady321/plinth.git@v0.5.0"
```

Add the `ui` extra for the researcher UI: `"plinth[ui] @ git+https://…"`.

## Modules for application code

| Module | What you use it for |
|--------|---------------------|
| `plinth.base_stage` | `BaseStage`, the class every stage subclasses |
| `plinth.intent` | `StageIntent`, what a stage reads, writes and does to row count |
| `plinth.results` | `StageOutcome`: `update`, `filter`, `expand`, `aggregate` |
| `plinth.registry` | `StageRegistry`, empty until your application registers stages |
| `plinth.rows` | `CoreManifestRow`, `ManifestRow` typing aids |
| `plinth.context` | `StageContext` and its in-memory and filesystem implementations |
| `plinth.dataset.identity` | `ManifestIdentity`, entity and hierarchy keys |
| `plinth.dataset.media` | `MediaSpec`, the file-pointer column; `NO_SOURCE_FILE` |
| `plinth.dataset.structures` | `DatasetSchema`, `DatasetManifest`, `MetadataLedger` |
| `plinth.config` | `PipelineConfig`, YAML load and save |
| `plinth.dag_structures` | Typed DAG builders |
| `plinth.validation` | `validate_pipeline_config` |
| `plinth.layout` | `DataLayout`, where runs are written |
| `plinth.experiment_launcher` | `ExperimentLauncher`, validate-then-run entry point |
| `plinth.runtime.pipeline` | `Pipeline`, for finer control over a run |
| `plinth.testing` | Hermetic test harness (`InMemoryStageContext`, `TypicalStageExecutor`, `run_typical_stage`, `minimal_manifest`) |

## Stability

| Level | Modules | Promise |
|-------|---------|---------|
| Stable | Everything in the table above | Breaking changes only in a minor release before 1.0 (a major one after), listed in the [changelog](../CHANGELOG.md) |
| Internal | `plinth.runtime.*` other than `pipeline`, `plinth.blocks`, `plinth.block_executors`, `plinth.address.*`, `plinth.flow.*`, `plinth.dataset.manifest_paths` | May change in any release; import only when extending plinth itself |

`plinth/__init__.py` exports only `__version__` for now; import from the modules above.

## What plinth never imports

Plinth depends on pandas, PyYAML, tqdm and jsonschema (plus FastAPI, uvicorn, pydantic and httpx
with the `ui` extra) and nothing else. It never imports your stage packages, your registration
code, your entry scripts or your pipeline configs: dependencies point from your application to
plinth only.

Three checks keep it that way:

| Check | Where |
|-------|-------|
| `library-domain-free` import-linter contract (no ML frameworks in the core) | `.importlinter`, run in CI as `lint-imports` |
| Declared dependencies match what the package imports | `tests/adoption/test_domain_neutrality.py` |
| A clean subprocess imports plinth and finds an empty registry | `tests/adoption/test_import_smoke.py` |
