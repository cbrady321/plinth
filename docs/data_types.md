# Working with any data type

Plinth never opens your data. The runtime sees **manifest rows** and, optionally, **one file path per
row**; decoding, models and domain rules live in your stage bodies. The same engine therefore runs a
pipeline over database exports, documents, images, audio, video, sensor logs or anything else stored
as rows and files.

Each pattern below has a runnable, dependency-free script in [`examples/`](../examples/README.md),
executed in CI by `tests/invariants/test_data_type_examples.py`.

## The two declarations

A dataset describes itself once, in `dataset_schema.yaml` (a `DatasetSchema`):

| Declaration | Question it answers | Default |
|-------------|---------------------|---------|
| `identity` (`ManifestIdentity`) | What identifies a row? An entity key plus optional hierarchy keys below it | `entity_id`, no hierarchy |
| `media` (`MediaSpec`) | Which column points at the row's file, and where are files written? | `file_path`, `files/` |

Nothing else about the data type is assumed. Pick names that read naturally for your domain:

```python
from plinth.dataset.identity import ManifestIdentity
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetSchema

video = DatasetSchema(
    identity=ManifestIdentity(
        entity_key="video_id",
        hierarchy_keys=["frame"],
        key_types={"frame": "optional_int"},  # empty on clip rows, an int on frame rows
    ),
    media=MediaSpec(path_column="media_path", subdir="media"),
)
```

## Patterns by data type

| Data | Typical row | Identity | Media | Common stage shapes | Example |
|------|-------------|----------|-------|---------------------|---------|
| Tabular records | one record / event / order line | `customer_id` → `order_id` | none: rows carry no file | filter, enrich, `group_by` aggregate | [`tabular_records.py`](../examples/tabular_records.py) |
| Text | one document, later one chunk | `doc_id` → `paragraph` (`int`) | `text_path`, `texts/` | expand into chunks, measure, filter, aggregate | [`text_documents.py`](../examples/text_documents.py) |
| Images | one image | `image_id` | `image_path`, `images/` | probe, filter, parallel branches, sidecar report | [`images.py`](../examples/images.py) |
| Audio | one recording / track | `album` → `track` | `track_path`, `tracks/` | probe, filter, rewrite files, aggregate | [`audio_tracks.py`](../examples/audio_tracks.py) |
| Video | one clip, later one frame | `video_id` → `frame` (`optional_int`) | `media_path`, `media/` | probe, expand into frames, measure, aggregate | [`video.py`](../examples/video.py) |

Other workloads map onto the same shapes. A sensor log is a tabular dataset, or one file per device
with `device_id` → `window`. A PDF corpus is text with `page` as a hierarchy key. A point-cloud or
volumetric scan is "images" with a different decoder.

### Rows without files

When a row's `<path_column>` is empty or absent, `process_file` receives
`input_path == plinth.dataset.media.NO_SOURCE_FILE`, and nothing is copied or propagated. Declare
`reads_files=False`. A stage that declares `reads_files=True` fails on such rows instead of
silently skipping them.

### Many rows from one file (chunks, tiles, frames, pages)

Declare `expands_rows=True` (plus `modifies_files=True` when you write the pieces) and return
`StageOutcome.expand([...])`. Each new row sets its hierarchy key and points `<path_column>` at
`<subdir>/<piece name>`, written next to `output_path`:

```python
name = f"{metadata['doc_id']}_p{number:03d}.txt"
(output_path.parent / name).write_text(paragraph)
rows.append({**metadata, "paragraph": number, "text_path": f"texts/{name}"})
```

Collapse the pieces later with `group_by` + `process_group()` + `StageOutcome.aggregate()` (see the
[grouping recipe](recipes/grouping.md)). The aggregated row keeps the group keys,
and its hierarchy keys fall back to `key_defaults`, or stay empty for `optional_int`.

### Rewriting files (transcode, resize, normalize)

Declare `modifies_files=True` and write the result to the `output_path` the engine hands you. It is
`<stage dir>/<subdir>/<file name>`, so the row's relative `<path_column>` value stays valid for every
later stage.

### Results that are not rows (reports, indexes, embeddings)

Write them as sidecar files in `finalize_output(context, output_dir)` and leave the manifest as is.
The images example writes `camera_report.csv` this way.

### Several files per row (multimodal)

`MediaSpec` names the one file the engine resolves, propagates and hands to `process_file` as
`input_path`. Keep additional per-row files (a subtitle track next to a video, a mask next to an
image) in ordinary manifest columns and open them yourself, relative to `context.get_input_dir()`.
Alternatively, model each modality as its own row under a shared entity key.

## How file references flow between stages

- A stage with `modifies_files=False` passes `<path_column>` values through unchanged and copies
  nothing. Relative values keep resolving downstream: the runtime looks in the stage input directory
  first, then in each upstream stage directory recorded in the ledger, nearest first. A file-reading
  stage after any number of metadata-only stages therefore receives the original file, or the most
  recently rewritten copy.
- A stage with `modifies_files=True` owns the file at `output_path`. Downstream stages resolve the
  same relative value to that new file, because it is the nearest one.
- Absolute values are used as-is. Prefer relative values so runs stay relocatable.
- The upstream lookup never follows a `../` escape out of an upstream directory, and
  `FileSystemStageContext.get_input_path()` rejects paths outside the input and upstream directories.
- Manifests are trusted input. Absolute values, and relative values containing `../` resolved
  against the stage input directory, are followed as written, so a manifest can point a stage at any
  file the process can read. Build manifests yourself or take them only from trusted sources.
