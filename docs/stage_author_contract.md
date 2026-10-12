# Stage Author Contract

Version: 1.0.0

Authoritative surface for writing typical pipeline stages.

## Typical stage shape

1. Subclass `BaseStage`
2. Implement `get_intent() -> StageIntent`
3. Implement `process_file(...) -> StageOutcome`
4. Leave `execute()` alone; only stages registered with `mode="exceptional"` replace it

The engine calls `TypicalStageExecutor`, which owns manifest iteration, ledger writes, schema updates, and propagation.

Use `process_file` / `process_group` with `StageOutcome` — the sole row-processing hooks invoked by the runtime.

## StageIntent

Declare what the stage reads and writes. Key fields:

| Field | Purpose |
|-------|---------|
| `required_input_columns` | Manifest columns required before execution |
| `write_columns` | Columns the stage promises to produce |
| `append_to_unique_key` | Additional unique-key dimensions |
| `modifies_files` | Whether output files are written |
| `reads_files` | Whether input files are read from disk |
| `filters_rows` / `expands_rows` / `aggregates_rows` | Structural manifest changes |
| `group_by` | Use `process_group()` instead of row iteration |
| `allow_partial_success` | Opt-in: continue after row failures (default `false`) |
| `max_dropped_rows` | When partial success enabled, fail if drops exceed this count (`null` = unlimited) |

Call `intent.validate_strict()` in tests; plinth also validates every intent when the stage is loaded.

## Row failure policy

By default a stage is **fail-fast**: the first row whose `process_file()` or `process_group()` raises fails the stage, and the error names the row index and the cause.

Set `allow_partial_success=True` when losing some rows is acceptable. Failed rows are then dropped and counted in the stage's ledger entry. Add `max_dropped_rows` to fail the stage anyway once more than that many rows have been dropped.

## StageOutcome (sole channel)

Return typed outcomes — not raw dicts:

```python
from plinth.results import StageOutcome

return StageOutcome.update(file_path="files/foo.txt", category="b")
return StageOutcome.filter()
return StageOutcome.expand([{...}, {...}])
return StageOutcome.aggregate(entity_id="s1", chunk_count=3)
```

Plain dict returns are rejected with `TypeError`. Use `StageOutcome` only.

## Registration

Your application registers its stages, typically from one `register_stages()` function called at startup. Importing `plinth` registers nothing.

```python
from plinth.registry import StageRegistry

@StageRegistry.register("my_stage", mode="typical")
class MyStage(BaseStage):
    ...
```

## Exceptional stages

A stage registered with `mode="exceptional"` overrides `execute(context)` and runs its own logic instead of the row loop. See [Choosing a stage kind](stage_kinds.md) for when that is justified.

Without the row loop, the bookkeeping the runtime normally does becomes the stage's job. When `execute()` returns, the runtime verifies each item below and fails the stage, naming the item, if one is missing:

| The stage must… | Using |
|-----------------|-------|
| write into the directory it was given, and nowhere else | `context.get_output_dir()` |
| say up front which extra files it produces, beyond manifest, schema and ledger | registration metadata |
| hand back the manifest it produced (`replace=True` for a brand-new one) | `context.update_manifest(...)` |
| persist the schema next to that manifest | `context.save_schema(...)` |
| leave a single ledger entry describing this stage | `LedgerWriter` |

Plinth itself registers no stages of either kind.

## Parallel blocks

Parallel blocks run independent branches with **deterministic serial execution** and default **fail-fast** policy (`parallel_error_policy: fail_fast`): the first branch failure aborts the entire parallel block and the pipeline run. Branches are not executed concurrently at the OS level. `parallel_error_policy: continue` lets the remaining branches run after a failure. The block's output is then incomplete, and a downstream stage that needs every branch's columns fails, so prefer `fail_fast` whenever lineage must be complete.

## Propagation and file paths

The column that points at each row's file, the output subdirectory and the optional file-name column are declared by `DatasetSchema.media` (a `MediaSpec`; default `path_column="file_path"`, `subdir="files"`, `name_column=""`). See §Dataset schema. Everything below uses `<path_column>` and `<subdir>` from that spec.

- Prefer relative `<path_column>` values (`<subdir>/<file name>`) in manifest rows unless the stage modifies files in place
- Manifests are trusted input: absolute `<path_column>` values and relative values containing `../` are followed as written against the stage input directory (only the upstream fallback is confined to each upstream directory), so take manifests only from trusted sources
- When `modifies_files=False`, downstream stages receive path references to upstream files: a relative `<path_column>` value resolves against the stage input directory first, then against each upstream directory recorded in the ledger (nearest first), so file readers work after any number of metadata-only stages
- Output files are named by `<name_column>` when declared and set, else by the basename of `<path_column>`
- Rows whose `<path_column>` is empty or absent (e.g. purely tabular data) reach `process_file` with `input_path == plinth.dataset.media.NO_SOURCE_FILE`; they fail only if the stage declares `reads_files=True`, and they are never propagated
- Golden equivalence normalizes `<path_column>` to `<subdir>/<file name>` (`MediaSpec.portable_path`) for portable snapshots
- Multi-input contexts require all inputs to declare the same `media` spec (and identity)

## JSONPath skip and resume

Skip/resume selectors must resolve to directories produced by `NodeAddressResolver`. Do not construct stage paths manually. Integration tests in `tests/invariants/test_address_consumer_agreement.py` cover skip/resume agreement.

Out-of-range JSONPath indices (e.g. `children[99]`) raise `ValueError` at pipeline start — they do not silently run the full DAG.

When resuming from a stage, upstream stage `params` must match the hashes recorded in preserved ledger entries. Changing upstream params requires a full re-run or an earlier start point.

## Export (`export_flags`)

Per-stage `export_flags` in `PipelineConfig` copy the stage output tree to `{experiment_dir}/export/{stage_dir_name}/` after successful execution. Export is a side effect only: manifests and ledgers in the stage directory are unchanged. The ledger entry for an exported stage may record `exported_to` in `params`.

Test export trees are gitignored under fixture work directories.

Stages that consume multiple upstream directories receive a `MultiInputStageContext`. The engine merges manifests and ledgers from all input dirs before execution:

- Merge uses schema `unique_key` for row alignment
- Ledger entries from all inputs are concatenated in discovery order
- Parallel block aggregation uses the same merge path before downstream sequential stages
- Exemplar: parallel join in GT3 (`tests/fixtures/golden_pipeline/tiers/gt3/`)

Exceptional merge stages must follow the exceptional obligations checklist.

## Grouping

To produce one output row per key (per document, per album, per customer), set `group_by` and `aggregates_rows=True` on the intent and return `StageOutcome.aggregate()` from `process_group()`. Files that summarize the whole stage belong in `finalize_output()`.

Full recipe: [Grouping](recipes/grouping.md).

## Directory layout

Stage output directories are derived by `NodeAddressResolver` — stages must not compute location codes independently.

## Dataset schema: identity and file pointers

Each dataset declares its conventions once, in a `DatasetSchema` persisted as `dataset_schema.yaml` in every stage directory. Nothing about the kind of data (tabular, text, images, audio, video, …) is assumed — see [Working with any data type](data_types.md): the defaults describe a flat table whose optional file column is `file_path`.

```python
from plinth.dataset.identity import ManifestIdentity
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetSchema

schema = DatasetSchema(
    identity=ManifestIdentity(
        entity_key="entity_id",
        hierarchy_keys=["page"],          # rows are pages of a document
        key_types={"page": "int"},       # coerce + match as integers
        key_defaults={"page": 1},        # value for missing cells / missing column
    ),
    media=MediaSpec(path_column="text_path", subdir="texts"),
)
```

| Declaration | Default | Role |
|-------------|---------|------|
| `identity.entity_key` | `entity_id` | Primary entity identifier |
| `identity.hierarchy_keys` | `[]` | Optional tiers below the entity (added to the unique key; created when missing) |
| `identity.disambiguator` | `""` | Optional column that disambiguates rows when the hierarchy is incomplete |
| `identity.key_types` | `{}` | Per-column normalization: `int` (coerced, filled from `key_defaults`, matched as int) or `optional_int` (missing stays `None`, matched as int) |
| `identity.key_defaults` | `{}` | Fill values for hierarchy columns / `int` keys |
| `identity.column_aliases` | `{}` | Ingest renames, e.g. `{"record_id": "entity_id"}` |
| `media.path_column` | `file_path` | Column holding each row's file path |
| `media.subdir` | `files` | Output subdirectory for files written or propagated by a stage |
| `media.name_column` | `""` | Column holding the file name; empty = basename of the path |
| `unique_key` | `[]` | Explicit merge key; empty = identity columns present on both sides |

`dataset_schema.yaml` is written with every field explicit and `schema_format: 1`. A schema file without `schema_format`, or with another format, is rejected. A directory without `dataset_schema.yaml` uses `DatasetSchema()`.

## Manifest keys

The default unique key derives from `DatasetSchema.identity`: `entity_key`, then `hierarchy_keys`, then `disambiguator`, keeping those present on both sides of a merge. With the defaults that is just `entity_id`.

## Manifest row protocol

Manifest rows are open dictionaries at runtime. Plinth types only the keys it defines; validation is driven by `DatasetSchema` at merge boundaries.

### Plinth-defined keys (`CoreManifestRow`)

| Key | Role |
|-----|------|
| `entity_id` | Entity identifier under the default `entity_key` |
| `source_path` | Set by the runtime on `process_file` metadata: resolved input path, or `str(NO_SOURCE_FILE)`. Never persisted: dropped from returned rows and updates. If the input manifest has its own `source_path` column, the runtime leaves that value untouched instead; the resolved path is always the `input_path` argument |

CSV ingest applies the schema's `identity.column_aliases`. Author stages against `entity_id` or your schema's `entity_key`, and read file paths through your schema's `media.path_column`.

### Dataset extension

Stages may read and write any additional columns. Declare new output columns in `StageIntent.write_columns`. Type your dataset's columns with your own `TypedDict` extending `CoreManifestRow` (see §Static typing).

### Normalization

- Entity values normalized via `normalize_entity_id` (missing stays null, not `"nan"`).
- Use `.get()` for optional keys; structural stages may emit partial rows during expand/aggregate.

### Static typing

```python
from typing import cast

from plinth.rows import CoreManifestRow


class DocumentRow(CoreManifestRow, total=False):
    page: int
    text_path: str


def process_file(self, input_path, output_path, metadata: CoreManifestRow) -> StageOutcome:
    row = cast(DocumentRow, metadata)  # keep the base signature; narrowing it breaks the override
    page = row.get("page", 1)
    ...
```

Use `manifest.df`, row dicts from `manifest[i]`, or `plinth.testing.minimal_manifest()` — not parallel list accessors on `DatasetManifest`.

### Anti-patterns

- Returning a bare dict from `process_file` (use `StageOutcome`)
- Assuming every row has all core keys populated before your stage runs
- Hard-coding absolute `<path_column>` values when `modifies_files=False`
- Assuming a hierarchy (`page`, `frame`, …) or a `filename` column the schema does not declare

## Testing without filesystem

Use `plinth.testing` for hermetic tests. See [testing_recipe.md](testing_recipe.md).

```python
from plinth.testing import minimal_manifest, run_typical_stage

context = run_typical_stage(stage, [{"entity_id": "s1", "file_path": "files/a.txt"}])
# pass schema=... when your dataset declares identity keys or a different file column
```

`plinth.context` remains the production API; `plinth.testing` provides harness helpers and stable imports.

## Appendix: every `StageIntent` field

| Field | Set it when… | For example |
|-------|--------------|-------------|
| `required_input_columns` | the stage cannot run unless these columns exist | `{"album"}` for a stage that groups by album |
| `write_columns` | the stage produces columns (name → type description) | `{"word_count": "int"}` |
| `append_to_unique_key` | new rows need an extra key to stay distinct | `{"paragraph"}` after splitting documents into paragraphs |
| `modifies_files` | the stage writes new or changed files | `True` for a resizer; `False` when only columns change |
| `reads_files` | the stage opens each row's file | `False` for a filter that looks only at columns |
| `replaces_manifest` | rarely: a full rebuild that none of the row-shape flags describe | prefer `filters_rows` / `expands_rows` / `aggregates_rows` |
| `filters_rows` | some rows may be dropped | an allowlist or quality filter |
| `expands_rows` | one row may become several | page → paragraphs, image → tiles, clip → frames |
| `aggregates_rows` | several rows become one | tracks → album, set together with `group_by` |
| `modify_columns` | the stage overwrites columns that already exist | `{"text_path"}` when it rewrites the files those paths point to |
| `group_by` | the stage works on groups, through `process_group()` | `["album"]` |
| `allow_partial_success` | losing a few failing rows is acceptable | a best-effort metadata probe |
| `max_dropped_rows` | partial success is on, but only up to a limit | `10` |

See [Choosing a stage kind](stage_kinds.md) for typical vs exceptional.
