"""Images: probe, filter, then measure and thumbnail in parallel branches before a per-camera report.

Each manifest row is one grayscale image (binary PGM). The pipeline

1. ``probe_images``        reads every image header (width, height),
2. ``drop_small_images``   filters out images whose shorter side is below ``min_side``,
3. a parallel block with two independent branches over the same rows:
   - ``measure_brightness`` records mean brightness (metadata only),
   - ``make_thumbnails``    writes a downscaled copy of every image (new files),
4. ``camera_report``       keeps every row and writes a per-camera summary sidecar (``camera_report.csv``)
   next to the manifest.

Run it::

    python examples/images.py [workdir]

PGM keeps the example dependency-free; in a real project use Pillow, OpenCV or a vision model inside
the stage bodies — the manifest, file propagation and branch merge are unchanged.
"""

from __future__ import annotations

import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.config import PipelineConfig
from plinth.context import StageContext
from plinth.dataset.identity import ManifestIdentity
from plinth.dataset.manifest_paths import dataset_schema_path, manifest_csv_path
from plinth.dataset.media import MediaSpec
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.experiment_launcher import ExperimentLauncher
from plinth.intent import StageIntent
from plinth.registry import StageRegistry
from plinth.results import StageOutcome

SCHEMA = DatasetSchema(
    identity=ManifestIdentity(entity_key="image_id"),
    media=MediaSpec(path_column="image_path", subdir="images"),
)

# --------------------------------------------------------------------------- stages


class ProbeImagesStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"image_path"},
            write_columns={"width": "int", "height": "int"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        width, height, _ = read_pgm(input_path)
        return StageOutcome.update(width=width, height=height)


class DropSmallImagesStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"width", "height"},
            filters_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        if min(int(metadata["width"]), int(metadata["height"])) < int(self.config.get("min_side", 1)):
            return StageOutcome.filter()
        return StageOutcome.update()


class MeasureBrightnessStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"image_path"},
            write_columns={"brightness": "float"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        _, _, pixels = read_pgm(input_path)
        return StageOutcome.update(brightness=round(sum(pixels) / len(pixels) / 255, 4))


class MakeThumbnailsStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"image_path"},
            write_columns={"thumb_width": "int", "thumb_height": "int"},
            reads_files=True,
            modifies_files=True,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        factor = int(self.config.get("factor", 2))
        width, height, pixels = read_pgm(input_path)
        small_w, small_h = width // factor, height // factor
        small = bytearray()
        for y in range(small_h):
            for x in range(small_w):
                block = [pixels[(y * factor + dy) * width + x * factor + dx] for dy in range(factor) for dx in range(factor)]
                small.append(sum(block) // len(block))
        write_pgm(output_path, small_w, small_h, bytes(small))
        return StageOutcome.update(thumb_width=small_w, thumb_height=small_h)


class CameraReportStage(BaseStage):
    """Leaves the manifest as is; the per-camera summary is a sidecar written in ``finalize_output``."""

    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"camera", "brightness"},
            reads_files=False,
            modifies_files=False,
        )

    def prepare_context(self, context: StageContext) -> None:
        self._brightness: Dict[str, List[float]] = defaultdict(list)

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        self._brightness[str(metadata["camera"])].append(float(metadata["brightness"]))
        return StageOutcome.update()

    def finalize_output(self, context: StageContext, output_dir: Path) -> Path:
        report = pd.DataFrame(
            [
                {"camera": camera, "image_count": len(values), "mean_brightness": round(sum(values) / len(values), 4)}
                for camera, values in sorted(self._brightness.items())
            ]
        )
        report.to_csv(output_dir / "camera_report.csv", index=False)
        return output_dir


def register_stages() -> None:
    StageRegistry.register("probe_images", mode="typical")(ProbeImagesStage)
    StageRegistry.register("drop_small_images", mode="typical")(DropSmallImagesStage)
    StageRegistry.register("measure_brightness", mode="typical")(MeasureBrightnessStage)
    StageRegistry.register("make_thumbnails", mode="typical")(MakeThumbnailsStage)
    StageRegistry.register("camera_report", mode="typical")(CameraReportStage)


CONFIG = PipelineConfig(
    name="images",
    version="1.0",
    dag={
        "type": "sequential",
        "name": "root",
        "children": [
            {"type": "stage", "name": "probe_images"},
            {"type": "stage", "name": "drop_small_images"},
            {
                "type": "parallel",
                "name": "analyze",
                "children": [
                    {"type": "stage", "name": "measure_brightness"},
                    {"type": "stage", "name": "make_thumbnails"},
                ],
            },
            {"type": "stage", "name": "camera_report"},
        ],
    },
    params={"drop_small_images": {"min_side": 8}, "make_thumbnails": {"factor": 2}},
)

# --------------------------------------------------------------------------- PGM helpers + synthetic dataset


def read_pgm(path: Path) -> Tuple[int, int, bytes]:
    """Read a binary (P5, 8-bit) PGM image: ``(width, height, pixels)``."""
    data = path.read_bytes()
    fields: List[bytes] = []
    pos = 0
    while len(fields) < 4:
        while data[pos : pos + 1].isspace():
            pos += 1
        start = pos
        while not data[pos : pos + 1].isspace():
            pos += 1
        fields.append(data[start:pos])
    if fields[0] != b"P5" or fields[3] != b"255":
        raise ValueError(f"{path}: not an 8-bit binary PGM")
    width, height = int(fields[1]), int(fields[2])
    return width, height, data[pos + 1 : pos + 1 + width * height]


def write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"P5\n%d %d\n255\n" % (width, height) + pixels)


def build_dataset(root: Path) -> Path:
    """Write four gradient images from two cameras (one too small), plus manifest and schema."""
    images = [("i1", "north", 32, 24, 40), ("i2", "north", 32, 24, 160), ("i3", "south", 16, 16, 100), ("i4", "south", 4, 4, 0)]
    rows = []
    for image_id, camera, width, height, base in images:
        pixels = bytes(min(255, base + (x + y) * 2) for y in range(height) for x in range(width))
        write_pgm(root / "images" / f"{image_id}.pgm", width, height, pixels)
        rows.append({"image_id": image_id, "camera": camera, "image_path": f"images/{image_id}.pgm"})
    DatasetManifest(pd.DataFrame(rows), schema=SCHEMA).to_csv(manifest_csv_path(root))
    SCHEMA.to_yaml(dataset_schema_path(root))
    return root


# --------------------------------------------------------------------------- entry point


def main(workdir: Path) -> pd.DataFrame:
    register_stages()
    dataset = build_dataset(workdir / "data" / "pipeline" / "publish" / "dataset")
    result = ExperimentLauncher(workdir).run(CONFIG, "images", input_source=str(dataset))
    manifest = DatasetManifest.from_csv(manifest_csv_path(result.output_dir), schema=SCHEMA)
    columns = ["image_id", "camera", "width", "height", "brightness", "thumb_width", "thumb_height"]
    print(manifest.df[columns].to_string(index=False))
    report = next(result.output_dir.parent.rglob("camera_report.csv"))
    print(f"\n{report.name}:\n{pd.read_csv(report).to_string(index=False)}")
    print(f"\nRun directory: {result.output_dir}")
    return manifest.df


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="plinth-images-")))
