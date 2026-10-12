# Plinth

[![Test](https://github.com/cbrady321/plinth/actions/workflows/test.yml/badge.svg)](https://github.com/cbrady321/plinth/actions/workflows/test.yml)
![Python 3.11–3.14](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Reproducible ML data pipelines — DAG runtime, manifest lineage, and typed stage contracts.

## Overview

Plinth is an execution engine for multi-stage machine-learning data pipelines — dataset curation, preprocessing, feature extraction, training-set assembly and evaluation — over any kind of data: tabular records, text, images, audio, video or any other files. The same runtime also serves general ETL jobs. It separates **what a stage does** (domain logic in your application) from **how pipelines run** (DAG traversal, manifest propagation, ledger writes, on-disk layout, resume, and validation).

A pipeline in Plinth is a directed acyclic graph of **stages**. Each stage reads a **manifest** — a table of rows describing the dataset (entities, file pointers, attributes) — and returns typed **outcomes** that tell the engine how to update the manifest. The engine writes a **metadata ledger** at every stage boundary so runs are reproducible and resumable.

Application stages plug into Plinth; Plinth never imports domain application code. Plinth ships with an empty stage registry — your application registers its own stages at startup.

### Core concepts

| Concept | Role |
|---------|------|
| **Manifest** | Tabular dataset index (`manifest.csv`) — one row per item (a record, a file, a chunk of a document, an entity, …) |
| **DatasetSchema** | Per-dataset declarations persisted as `dataset_schema.yaml`: identity keys (`ManifestIdentity`) and the file-pointer column (`MediaSpec`) |
| **StageIntent** | Declares what columns a stage reads/writes and how it changes manifest shape |
| **StageOutcome** | Typed return value from `process_file()` / `process_group()` — update, filter, expand, or aggregate |
| **StageContext** | Gives a stage access to input/output dirs, manifest, schema, and ledger |
| **PipelineConfig** | YAML-defined DAG topology, per-stage params, and run controls |
| **Ledger** | Append-only chain of stage hashes — enables resume and lineage validation |

### Execution model

```
Input dataset
     │
     ▼
┌─────────────┐    manifest.csv + dataset_schema.yaml
│  Stage 1    │──► metadata_ledger.yaml (hash chain entry)
└─────────────┘
     │
     ▼
┌─────────────┐    updated manifest.csv
│  Stage 2    │──► metadata_ledger.yaml
└─────────────┘
     │
     ▼
  … sequential, parallel, or nested blocks …
```

**Typical stages** implement `process_file()` (or `process_group()` when grouping) and return `StageOutcome`. The engine owns row iteration, schema updates, ledger writes, and file propagation.

**Exceptional stages** override `execute()` for cases that do not fit a row loop — manifest bootstrap, multi-root merge. Runtime obligation checks enforce correct manifest handoff and ledger writes.

### Any data type

Plinth never opens your data: it tracks rows, one optional file path per row, and lineage. Each dataset declares what identifies a row and which column points at its file, then stages bring their own decoders and models. Runnable, dependency-free pipelines in [`examples/`](examples/README.md):

| Data | Example | Shows |
|------|---------|-------|
| Tabular records | [`tabular_records.py`](examples/tabular_records.py) | rows with no files, column aliases, per-customer aggregation |
| Text | [`text_documents.py`](examples/text_documents.py) | documents → paragraphs → per-document stats |
| Images | [`images.py`](examples/images.py) | parallel branches (measure ‖ thumbnail), sidecar report |
| Audio | [`audio_tracks.py`](examples/audio_tracks.py) | header probing, rewritten files, album → track hierarchy |
| Video | [`video.py`](examples/video.py) | clip → sampled frames → per-clip summary with cut detection |

```bash
python examples/video.py
```

See [docs/data_types.md](docs/data_types.md) for the patterns (chunking, rewriting files, multimodal rows, how file references flow between stages).

---

## When to use plinth

Plinth is a library, not a platform: no server, scheduler, database or cloud account. A pipeline is Python stages plus a YAML DAG, and every run is a directory of CSV manifests, schemas, files and a ledger.

Reach for it when you need:

- **Item-level lineage.** Every row of every stage's manifest is kept on disk, so you can trace any training example back through each filter, split and roll-up that produced it.
- **Typed row-shape changes.** Stages declare whether they update, filter, expand or aggregate rows, and return a matching `StageOutcome`. The engine rejects anything else, and catches parallel branches that write the same column at config time.
- **Tamper-evident runs.** Each stage boundary appends a hash of its inputs, outputs and parameters to a chained ledger, which is validated after every run; a resume refuses to build on upstream outputs made with different parameters.
- **Fast, hermetic stage tests.** `plinth.testing` runs a stage through the production lifecycle on an in-memory manifest.

Look elsewhere when:

| You need | Consider |
|----------|----------|
| Scheduling, retries, sensors and a deployment UI for production data assets | Dagster, Airflow, Prefect |
| Project templates, a data catalog and many I/O connectors for general data engineering | Kedro |
| Versioning large data files alongside Git, with remote storage and cached stages | DVC |
| Querying and transforming millions of files in object storage, distributed | DataChain, Ray Data |

Plinth works alongside these tools. For example, version its run directories with DVC, or call a plinth pipeline from an orchestrator task. Today it processes rows sequentially on one machine and reruns every stage downstream of the resume point; skipping unchanged stages and worker pools are on the roadmap.

---

## Install

```bash
pip install "plinth @ git+https://github.com/cbrady321/plinth.git@v0.5.0"
```

Add the researcher UI with `"plinth[ui] @ git+https://github.com/cbrady321/plinth.git@v0.5.0"`. Requires Python 3.11+.

To work on plinth itself, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Interface guide

### 1. Declaring intent — `StageIntent`

Every stage declares what it reads and writes before execution. The engine validates inputs, detects parallel-branch conflicts, and chooses manifest replace vs merge automatically.

```python
from plinth.intent import StageIntent

# Row filter — drops rows, no file I/O
filter_intent = StageIntent(
    required_input_columns={"filename"},
    filters_rows=True,
    modifies_files=False,
    reads_files=False,
)

# File inspector — reads each row's file, writes a new column
inspect_intent = StageIntent(
    required_input_columns={"file_path"},  # the column named by DatasetSchema.media.path_column
    write_columns={"byte_count": "int"},
    reads_files=True,
    modifies_files=False,
)

# Entity aggregation — collapses many rows to one per entity
aggregate_intent = StageIntent(
    required_input_columns={"entity_id"},
    write_columns={"file_count": "int", "total_bytes": "int"},
    group_by=["entity_id"],
    aggregates_rows=True,
    reads_files=False,
    modifies_files=False,
)
```

Call `intent.validate_strict()` in tests to catch misconfiguration early.

### 2. Returning outcomes — `StageOutcome`

Stages communicate results through typed outcomes — not raw dicts. Plain dict returns are rejected with `TypeError`.

```python
from plinth.results import StageOutcome

# Keep row, update columns
StageOutcome.update(file_path="files/foo.txt", clean_status="done")

# Drop row from manifest
StageOutcome.filter()

# Replace one row with multiple (e.g. splitting a document into chunks)
StageOutcome.expand([
    {"entity_id": "doc1", "chunk": 1, "text": "First chunk"},
    {"entity_id": "doc1", "chunk": 2, "text": "Second chunk"},
])

# Collapse a group to one row (used with group_by + process_group)
StageOutcome.aggregate(
    entity_id="doc1",
    chunk_count=12,
    total_bytes=4096,
)
```

### 3. Writing a typical stage — `BaseStage` + `StageRegistry`

Sections 3–7 build one small pipeline you can run as written: it keeps an allowlist of files, counts each file's bytes and lines in two parallel branches, then rolls the counts up per entity. Put the stages of sections 3 and 4 in `stages.py`.

Subclass `BaseStage`, implement `get_intent()` and `process_file()`, and register the class under the name your pipeline configs use. Do not override `execute()` unless the stage is exceptional.

```python
# stages.py
from pathlib import Path
from typing import Any, Dict, List

from plinth.base_stage import BaseStage
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome


@StageRegistry.register("allowlist_filter", mode="typical")
class AllowlistFilterStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"filename"},
            filters_rows=True,
            modifies_files=False,
            reads_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        if metadata["filename"] in self.config.get("allow", []):
            return StageOutcome.update()
        return StageOutcome.filter()


@StageRegistry.register("count_bytes", mode="typical")
class CountBytesStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"file_path"},
            write_columns={"byte_count": "int"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(byte_count=input_path.stat().st_size)


@StageRegistry.register("count_lines", mode="typical")
class CountLinesStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"file_path"},
            write_columns={"line_count": "int"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        return StageOutcome.update(line_count=len(input_path.read_text().splitlines()))
```

`input_path` is the row's file, resolved from the schema's `media.path_column` (`file_path` by default) against the stage's input directory. Registration happens on import, so your entry point imports the stage modules once before running anything.

### 4. Group aggregation — `process_group()`

When `StageIntent.group_by` is set, the engine calls `process_group()` once per group instead of `process_file()` once per row. Add this stage to `stages.py`:

```python
@StageRegistry.register("aggregate_by_entity", mode="typical")
class AggregateByEntityStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"entity_id", "byte_count", "line_count"},
            write_columns={"file_count": "int", "total_bytes": "int", "total_lines": "int"},
            group_by=["entity_id"],
            aggregates_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_group(
        self, group_keys: Dict[str, Any], rows: List[Dict[str, Any]], input_dir: Path, output_dir: Path
    ) -> StageOutcome:
        if len(rows) < self.config.get("min_rows", 1):
            return StageOutcome.filter()
        return StageOutcome.aggregate(
            entity_id=group_keys["entity_id"],
            file_count=len(rows),
            total_bytes=sum(int(r["byte_count"]) for r in rows),
            total_lines=sum(int(r["line_count"]) for r in rows),
        )
```

Override `prepare_context()` and `finalize_output()` as well if the stage loads or writes sidecar files.

### 5. Hermetic stage testing — `plinth.testing`

Test domain logic without touching the filesystem. `run_typical_stage` runs the same lifecycle as production (intent validation, outcome application, schema updates) against an in-memory manifest.

```python
# test_stages.py
from plinth.testing import run_typical_stage

from stages import AllowlistFilterStage


def test_allowlist_filter() -> None:
    stage = AllowlistFilterStage("allowlist_filter", {"allow": ["a.txt"]})
    context = run_typical_stage(
        stage,
        [
            {"entity_id": "s1", "filename": "a.txt"},
            {"entity_id": "s2", "filename": "b.txt"},
        ],
    )

    result = context.get_manifest()
    assert result is not None
    assert list(result.df["filename"]) == ["a.txt"]
```

For more control, build an `InMemoryStageContext` yourself and call `TypicalStageExecutor().run(stage, context)`; both come from `plinth.testing`.

### 6. Defining a pipeline DAG — `PipelineConfig`

A dataset is a directory holding `manifest.csv` (one row per item), an optional `dataset_schema.yaml`, and the files the rows point at. `input_source` in a pipeline config names that directory relative to `<project>/data/`; without it, runs read `data/pipeline/publish/dataset/` (see `DataLayout`). This script writes a five-file dataset to `data/dataset/`. Each project (`entity_id`) has several files, so the schema declares `filename` as a second identity key:

```python
# make_dataset.py
from pathlib import Path

import pandas as pd

from plinth.dataset.identity import ManifestIdentity
from plinth.dataset.structures import DatasetManifest, DatasetSchema

dataset = Path("data/dataset")
notes = {
    ("alpha", "plan.txt"): "Scope\nMilestones\nRisks\n",
    ("alpha", "notes.txt"): "Kickoff went well.\n",
    ("alpha", "draft.txt"): "Unreviewed.\n",
    ("beta", "plan.txt"): "Scope\nBudget\n",
    ("beta", "notes.txt"): "Waiting on data.\nFollow up Friday.\n",
}
rows = []
for (project, name), text in notes.items():
    path = dataset / "files" / project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    rows.append({"entity_id": project, "filename": name, "file_path": f"files/{project}/{name}"})

schema = DatasetSchema(identity=ManifestIdentity(hierarchy_keys=["filename"]))
DatasetManifest(pd.DataFrame(rows), schema=schema).to_csv(dataset / "manifest.csv")
schema.to_yaml(dataset / "dataset_schema.yaml")
```

Pipelines are defined in YAML. The DAG supports sequential blocks, parallel branches, and nesting. Here the two counting stages run as parallel branches over the same rows, and their columns are merged before aggregation:

```yaml
# config/my_pipeline.yaml
name: my_experiment
version: "1.0"
input_source: dataset

dag:
  type: sequential
  name: root
  children:
    - type: stage
      name: allowlist_filter
    - type: parallel
      name: inspect
      children:
        - type: stage
          name: count_bytes
        - type: stage
          name: count_lines
    - type: stage
      name: aggregate_by_entity

params:
  allowlist_filter:
    allow: ["plan.txt", "notes.txt"]
  aggregate_by_entity:
    min_rows: 2
```

The same DAG can be built in Python with the typed dataclasses in `plinth.dag_structures` (`DAGConfig`, `SequentialBlockConfig`, `ParallelBlockConfig`, `StageConfig`).

### 7. Running a pipeline — `ExperimentLauncher`

`ExperimentLauncher` validates the config against the registered stages, then runs it:

```python
# run.py
from pathlib import Path

import pandas as pd

import stages  # noqa: F401 — registers the stages
from plinth.config import PipelineConfig
from plinth.experiment_launcher import ExperimentLauncher
from plinth.validation import validate_pipeline_config

config = PipelineConfig.from_yaml(Path("config/my_pipeline.yaml"))
check = validate_pipeline_config(config)
if not check.ok:
    raise SystemExit("\n".join(check.errors))

result = ExperimentLauncher(project_root=Path(".")).run(config, experiment_name="first_run")
print(pd.read_csv(result.output_dir / "manifest.csv"))
```

```bash
python make_dataset.py
python run.py
```

The final manifest has one row per project: `alpha` keeps 2 of its 3 files (`draft.txt` is not on the allowlist), `beta` keeps both, and each row carries `file_count`, `total_bytes` and `total_lines`. `filename` is empty on these rows: it identified individual files, and an aggregated row describes the whole project (see the [grouping recipe](docs/recipes/grouping.md)).

Each stage writes to its own directory under `data/pipeline/runs/<experiment_name>/` (configurable with `DataLayout`), next to a copy of the config as `pipeline_config.yaml`. Every stage directory holds its `manifest.csv`, `dataset_schema.yaml` and `metadata_ledger.yaml`. To resume from a stage, reusing the outputs before it:

```python
result = ExperimentLauncher(project_root=Path(".")).run(
    config, experiment_name="first_run", start_from_stage="aggregate_by_entity"
)
```

Per-stage progress bars appear only when output goes to a terminal; set `TQDM_DISABLE=1` to turn them off there too. Logging uses the standard `logging` module under the `plinth` logger.

Use `plinth.runtime.pipeline.Pipeline` directly for finer control over stage filters and JSONPath-based skip and resume selectors.

### 8. Exceptional stages — `execute()` override

Use only when the typical row loop cannot express the operation — manifest bootstrap from an external export, multi-root merge, or full-manifest rebuild.

```python
from pathlib import Path

from plinth.base_stage import BaseStage
from plinth.context import StageContext
from plinth.registry import StageRegistry


@StageRegistry.register("bootstrap_import", mode="exceptional")
class BootstrapImportStage(BaseStage):
    def execute(self, context: StageContext) -> Path:
        output_dir = context.get_output_dir()
        # build manifest from external source
        # context.update_manifest(new_manifest, replace=True)
        # context.save_schema()
        # append ledger entry via context helpers
        return output_dir
```

Runtime obligation checks verify manifest handoff, schema save, ledger entry, and resolver-derived address before the stage boundary closes.

### 9. Researcher UI — analyze completed runs

Optional web UI for inspecting manifests, ledgers, failures, and cross-run comparisons.

```bash
plinth-researcher-ui --project-root .
```

Runs are read from `<project-root>/data/pipeline/runs/`. After the walkthrough above, `first_run` shows each stage's manifest, ledger entry and row counts.

The UI has no authentication. It binds to `127.0.0.1` and answers only requests addressed to this machine; pass `--host` to expose it elsewhere only on a network you trust.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/quickstart.md](docs/quickstart.md) | Zero to passing hermetic stage test in 30 minutes |
| [docs/data_types.md](docs/data_types.md) | Tabular, text, image, audio and video patterns |
| [examples/](examples/README.md) | Runnable end-to-end pipeline per data type |
| [docs/stage_author_contract.md](docs/stage_author_contract.md) | Authoritative stage API surface |
| [docs/stage_kinds.md](docs/stage_kinds.md) | Typical vs exceptional |
| [docs/testing_recipe.md](docs/testing_recipe.md) | Hermetic stage tests without filesystem |
| [docs/recipes/grouping.md](docs/recipes/grouping.md) | `group_by` + `StageOutcome.aggregate` |
| [docs/public_api.md](docs/public_api.md) | What to import and how stable it is |
| [docs/internals.md](docs/internals.md) | How the engine is put together |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup and checks |

## Version

`plinth.__version__` (in `src/plinth/version.py`), currently **0.5.0**.

## License

MIT — see [LICENSE](LICENSE).
