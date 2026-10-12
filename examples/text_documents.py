"""Text: split documents into paragraphs, measure them and roll the results back up per document.

Each input row is one plain-text document. The pipeline

1. ``split_paragraphs``      expands every document into one row (and one file) per paragraph,
2. ``count_words``           reads each paragraph and records its word and character counts,
3. ``drop_short_paragraphs`` filters out paragraphs under ``min_words``,
4. ``document_stats``        collapses the remaining paragraphs into one row per document.

Run it::

    python examples/text_documents.py [workdir]

The same shape fits any text workload — swap the stage bodies for a tokenizer, a language detector,
an embedding model or an LLM call; Plinth only tracks rows, files and lineage.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.dataset.identity import ManifestIdentity
from plinth.dataset.manifest_paths import dataset_schema_path, manifest_csv_path
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.experiment_launcher import ExperimentLauncher
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome

SCHEMA = DatasetSchema(
    identity=ManifestIdentity(
        entity_key="doc_id",
        hierarchy_keys=["paragraph"],  # 0 = the whole document, 1..n = its paragraphs
        key_types={"paragraph": "int"},
        key_defaults={"paragraph": 0},
    ),
    media=MediaSpec(path_column="text_path", subdir="texts"),
)

# --------------------------------------------------------------------------- stages


class SplitParagraphsStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"text_path"},
            expands_rows=True,
            reads_files=True,
            modifies_files=True,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        text = input_path.read_text(encoding="utf-8")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        rows = []
        for number, paragraph in enumerate(paragraphs, start=1):
            name = f"{metadata['doc_id']}_p{number:03d}.txt"
            (output_path.parent / name).write_text(paragraph + "\n", encoding="utf-8")
            rows.append({**metadata, "paragraph": number, "text_path": f"texts/{name}"})
        return StageOutcome.expand(rows)


class CountWordsStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"text_path"},
            write_columns={"word_count": "int", "char_count": "int"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        text = input_path.read_text(encoding="utf-8")
        return StageOutcome.update(word_count=len(text.split()), char_count=len(text.strip()))


class DropShortParagraphsStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"word_count"},
            filters_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        if int(metadata["word_count"]) < int(self.config.get("min_words", 1)):
            return StageOutcome.filter()
        return StageOutcome.update()


class DocumentStatsStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"doc_id", "word_count"},
            write_columns={"paragraph_count": "int", "total_words": "int"},
            group_by=["doc_id"],
            aggregates_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_group(
        self, group_keys: Dict[str, Any], rows: List[Dict[str, Any]], input_dir: Path, output_dir: Path
    ) -> StageOutcome:
        return StageOutcome.aggregate(
            doc_id=group_keys["doc_id"],
            title=rows[0]["title"],
            paragraph_count=len(rows),
            total_words=sum(int(r["word_count"]) for r in rows),
        )


def register_stages() -> None:
    StageRegistry.register("split_paragraphs", mode="typical")(SplitParagraphsStage)
    StageRegistry.register("count_words", mode="typical")(CountWordsStage)
    StageRegistry.register("drop_short_paragraphs", mode="typical")(DropShortParagraphsStage)
    StageRegistry.register("document_stats", mode="typical")(DocumentStatsStage)


CONFIG = PipelineConfig(
    name="text_documents",
    version="1.0",
    dag={
        "type": "sequential",
        "name": "root",
        "children": [
            {"type": "stage", "name": "split_paragraphs"},
            {"type": "stage", "name": "count_words"},
            {"type": "stage", "name": "drop_short_paragraphs"},
            {"type": "stage", "name": "document_stats"},
        ],
    },
    params={"drop_short_paragraphs": {"min_words": 4}},
)

# --------------------------------------------------------------------------- synthetic dataset

DOCUMENTS = {
    "d1": (
        "Field notes",
        "The river rose two feet overnight and the lower path is closed.\n\n"
        "Ok.\n\n"
        "Volunteers will rebuild the footbridge once the water drops below the marker.",
    ),
    "d2": (
        "Release notes",
        "This release adds resumable runs and a stricter manifest loader.\n\n"
        "Upgrade by reinstalling the package and re-running the validation scripts.",
    ),
}


def build_dataset(root: Path) -> Path:
    """Write the documents as UTF-8 text files plus ``manifest.csv`` and ``dataset_schema.yaml``."""
    rows = []
    for doc_id, (title, body) in DOCUMENTS.items():
        path = root / "texts" / f"{doc_id}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body + "\n", encoding="utf-8")
        rows.append({"doc_id": doc_id, "title": title, "text_path": f"texts/{doc_id}.txt"})
    DatasetManifest(pd.DataFrame(rows), schema=SCHEMA).to_csv(manifest_csv_path(root))
    SCHEMA.to_yaml(dataset_schema_path(root))
    return root


# --------------------------------------------------------------------------- entry point


def main(workdir: Path) -> pd.DataFrame:
    register_stages()
    dataset = build_dataset(workdir / "data" / "pipeline" / "publish" / "dataset")
    result = ExperimentLauncher(workdir).run(CONFIG, "text_documents", input_source=str(dataset))
    manifest = DatasetManifest.from_csv(manifest_csv_path(result.output_dir), schema=SCHEMA)
    print(manifest.df.to_string(index=False))
    print(f"\nRun directory: {result.output_dir}")
    return manifest.df


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="plinth-text-")))
