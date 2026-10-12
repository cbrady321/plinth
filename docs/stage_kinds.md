# Choosing a stage kind

Plinth has two kinds of stage. Almost every stage should be **typical**; reach for **exceptional**
only when the work cannot be described row by row or group by group.

| Kind | You write | Plinth handles |
|------|-----------|----------------|
| Typical (`mode="typical"`, the default) | `get_intent()` plus `process_file()` or `process_group()`, each returning a `StageOutcome` | Iterating the manifest, applying outcomes, propagating files, writing the schema and the ledger entry |
| Exceptional (`mode="exceptional"`) | `get_intent()` plus your own `execute(context)` | Checking afterwards that you handed back a manifest, saved the schema, appended one ledger entry and wrote to the resolver's directory |

## The one question to ask

> Can every row of this stage's output be computed from **one input row**, or from **one group of
> input rows** that share a key?

If yes, the stage is typical. The four outcomes cover the shapes this produces:

| Shape of the work | Outcome | Intent flag |
|-------------------|---------|-------------|
| Add or change columns on a row | `StageOutcome.update(...)` | `write_columns` |
| Drop a row | `StageOutcome.filter()` | `filters_rows=True` |
| Turn one row into several (chunks, tiles, clips) | `StageOutcome.expand([...])` | `expands_rows=True` |
| Turn a group of rows into one (roll-ups, summaries) | `StageOutcome.aggregate(...)` from `process_group()` | `group_by=[...]`, `aggregates_rows=True` |

Typical stages can still do whole-dataset work around the row loop: load a lookup table in
`prepare_context()` and write a summary file in `finalize_output()`.

If no, the stage is exceptional. In practice that means one of:

- **Creating a manifest** from something that is not a manifest yet — a directory of files, a
  database query, an API response or a vendor export. There is no input row to iterate over.
- **Rebuilding the whole manifest** from several inputs with alignment rules that the default
  merge on `unique_key` cannot express.

## Examples

| Stage | Kind | Why |
|-------|------|-----|
| Keep only documents in an allowlist | Typical | Each row is kept or dropped on its own (`filter`) |
| Measure each image's size | Typical | One row in, one row out with new columns (`update`) |
| Split each document into paragraphs | Typical | One row becomes several (`expand`); see [`examples/text_documents.py`](../examples/text_documents.py) |
| Roll tracks up into one row per album | Typical | One group becomes one row (`aggregate`); see [`examples/audio_tracks.py`](../examples/audio_tracks.py) |
| Build the first manifest by scanning a folder | Exceptional | Nothing to iterate yet |
| Load rows from a SQL query | Exceptional | The manifest comes from outside the pipeline |

## If you do write an exceptional stage

Register it with `mode="exceptional"` and follow the obligations in the
[author contract](stage_author_contract.md#exceptional-stages). The runtime checks them when the
stage returns and fails the run if one is missed. Keep exceptional stages few: they give up the
per-row guarantees (intent conformance, row-failure policy, file propagation) that typical stages
get for free.

## See also

- [Grouping recipe](recipes/grouping.md) — `group_by` with `process_group()` end to end
- [Testing recipe](testing_recipe.md) — unit-test a typical stage in memory
