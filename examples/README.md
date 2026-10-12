# Examples

One runnable pipeline per kind of data. Each script builds a small synthetic dataset, registers its
stages, runs the full DAG through `ExperimentLauncher` and prints the final manifest. Only the
standard library is used to read and write the media, so every example needs nothing beyond plinth
itself. Run them from a clone of this repository. In real projects, put your decoder or model of choice inside the stage bodies.

```bash
python examples/video.py             # writes to a fresh temp directory
python examples/video.py ./scratch   # or to a directory you choose
```

| Script | Data | Shows |
|--------|------|-------|
| [`tabular_records.py`](tabular_records.py) | order lines in a CSV, no files | `NO_SOURCE_FILE`, `column_aliases`, filter → enrich → `group_by` aggregate |
| [`text_documents.py`](text_documents.py) | plain-text documents | `expands_rows` into paragraphs, `int` hierarchy key, aggregate back per document |
| [`images.py`](images.py) | grayscale PGM images | parallel block (measure ‖ thumbnail), branch merge, sidecar report in `finalize_output` |
| [`audio_tracks.py`](audio_tracks.py) | WAV tracks | header probing, rewritten files (`modifies_files`), entity → hierarchy (`album` → `track`) |
| [`video.py`](video.py) | YUV4MPEG2 clips | frame sampling via `expands_rows`, `optional_int` key, per-clip summary with cut detection |

Each run leaves a full run tree under `<workdir>/data/pipeline/runs/<name>/`: per-stage manifests,
`dataset_schema.yaml`, the hash-chained `metadata_ledger.yaml`, and any files the stages wrote.
Browse it with `python -m plinth.researcher_ui --project-root <workdir>` (needs the `ui` extra).

See [docs/data_types.md](../docs/data_types.md) for the patterns behind these scripts.
`tests/invariants/test_data_type_examples.py` runs every example in CI.
