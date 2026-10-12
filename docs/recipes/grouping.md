# Grouping recipe: one output row per key

Use this when a downstream stage needs one row per *something* — per document after chunking, per
album after per-track analysis, per customer after per-order validation.

The runnable versions of this recipe are [`examples/audio_tracks.py`](../../examples/audio_tracks.py)
(tracks → albums) and [`examples/tabular_records.py`](../../examples/tabular_records.py)
(order lines → customers).

## 1. Declare the grouping in the intent

```python
from plinth.intent import StageIntent

def get_intent(self) -> StageIntent:
    return StageIntent(
        required_input_columns={"album", "duration_s"},
        write_columns={"track_count": "int", "total_duration_s": "float"},
        group_by=["album"],
        aggregates_rows=True,
        reads_files=False,
        modifies_files=False,
    )
```

Setting `group_by` makes the runtime call `process_group()` once per distinct key instead of
`process_file()` once per row. `aggregates_rows=True` tells it the manifest will shrink, so it
replaces the manifest rather than merging into it.

## 2. Return one outcome per group

```python
from plinth.results import StageOutcome

def process_group(self, group_keys, rows, input_dir, output_dir) -> StageOutcome:
    if len(rows) < self.config.get("min_tracks", 1):
        return StageOutcome.filter()          # drop the whole group
    return StageOutcome.aggregate(
        album=group_keys["album"],
        track_count=len(rows),
        total_duration_s=sum(float(r["duration_s"]) for r in rows),
    )
```

A grouping stage implements `process_group()` only; the runtime never calls `process_file()` when
`group_by` is set.

`rows` is the list of manifest rows in the group, as dicts. The aggregated row should carry the
group keys plus the new columns. Columns that identified the individual input rows (a track number,
a chunk index) no longer mean anything on the collapsed row: leave them out.

The output manifest still has a column for every identity key the schema declares. On an aggregated
row, hierarchy keys below the group keys hold the schema's `key_defaults` value, or are empty when no
default is declared. That marks the row as describing the whole group: in
[`text_documents.py`](../../examples/text_documents.py), `paragraph=0` means "the whole document".

## 3. Optional: whole-group side files

Two hooks run around the group loop:

- `prepare_context(context)` — runs once before the first group. Load anything every group needs,
  such as a lookup table from `context.get_input_dir()`.
- `finalize_output(context, output_dir)` — runs once after the last group. Write a summary file
  next to the manifest and return `output_dir`.

Do not override `execute()`; the runtime owns the loop, the manifest replace and the ledger entry.

## 4. Test it in memory

```python
from plinth.testing import run_typical_stage

context = run_typical_stage(
    AlbumRollupStage("album_rollup", {}),
    [
        {"entity_id": "t1", "album": "A", "duration_s": 200.0},
        {"entity_id": "t2", "album": "A", "duration_s": 180.0},
        {"entity_id": "t3", "album": "B", "duration_s": 240.0},
    ],
)
assert sorted(context.get_manifest().df["album"]) == ["A", "B"]
```

The in-memory harness runs the same lifecycle as a real pipeline. See the
[testing recipe](../testing_recipe.md) for more.
