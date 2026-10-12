"""Video: probe clips, sample frames, measure them and summarize each clip (including scene cuts).

Each input row is one video clip in YUV4MPEG2 (``.y4m``), the uncompressed format ffmpeg reads and
writes (``ffmpeg -i in.mp4 -pix_fmt gray out.y4m``). Rows are identified by ``video_id`` plus an
``optional_int`` ``frame`` key that is empty for clip-level rows. The pipeline

1. ``probe_videos``     reads each header and counts frames (width, height, fps, duration),
2. ``sample_frames``    expands every clip into one row per sampled frame, writing each frame as an image,
3. ``frame_brightness`` measures each sampled frame,
4. ``clip_summary``     collapses frames back to one row per clip, counting brightness jumps as cuts.

Run it::

    python examples/video.py [workdir]

In a real project decode with PyAV, OpenCV or ffmpeg and swap the per-frame measurement for any model;
Plinth tracks the clip → frame → clip lineage either way.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

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
        entity_key="video_id",
        hierarchy_keys=["frame"],
        key_types={"frame": "optional_int"},  # empty for clip-level rows, an int for frame rows
    ),
    media=MediaSpec(path_column="media_path", subdir="media"),
)

# --------------------------------------------------------------------------- stages


class ProbeVideosStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"media_path"},
            write_columns={"width": "int", "height": "int", "fps": "float", "frame_count": "int", "duration_s": "float"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        header, frames = read_y4m(input_path)
        count = sum(1 for _ in frames)
        return StageOutcome.update(
            width=header["width"],
            height=header["height"],
            fps=header["fps"],
            frame_count=count,
            duration_s=round(count / header["fps"], 3),
        )


class SampleFramesStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"media_path"},
            write_columns={"timestamp_s": "float"},
            expands_rows=True,
            reads_files=True,
            modifies_files=True,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        every = int(self.config.get("every_n_frames", 1))
        header, frames = read_y4m(input_path)
        rows = []
        for index, pixels in enumerate(frames):
            if index % every:
                continue
            name = f"{metadata['video_id']}_f{index:05d}.pgm"
            (output_path.parent / name).write_bytes(b"P5\n%d %d\n255\n" % (header["width"], header["height"]) + pixels)
            rows.append(
                {**metadata, "frame": index, "timestamp_s": round(index / header["fps"], 3), "media_path": f"media/{name}"}
            )
        return StageOutcome.expand(rows)


class FrameBrightnessStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"media_path"},
            write_columns={"brightness": "float"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        pixels = input_path.read_bytes().split(b"\n", 3)[3]
        return StageOutcome.update(brightness=round(sum(pixels) / len(pixels) / 255, 4))


class ClipSummaryStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"video_id", "frame", "brightness"},
            write_columns={"sampled_frames": "int", "mean_brightness": "float", "cut_count": "int"},
            group_by=["video_id"],
            aggregates_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_group(
        self, group_keys: Dict[str, Any], rows: List[Dict[str, Any]], input_dir: Path, output_dir: Path
    ) -> StageOutcome:
        threshold = float(self.config.get("cut_threshold", 0.25))
        series = [float(r["brightness"]) for r in sorted(rows, key=lambda r: int(r["frame"]))]
        cuts = sum(1 for before, after in zip(series, series[1:]) if abs(after - before) >= threshold)
        return StageOutcome.aggregate(
            video_id=group_keys["video_id"],
            duration_s=rows[0]["duration_s"],
            sampled_frames=len(rows),
            mean_brightness=round(sum(series) / len(series), 4),
            cut_count=cuts,
        )


def register_stages() -> None:
    StageRegistry.register("probe_videos", mode="typical")(ProbeVideosStage)
    StageRegistry.register("sample_frames", mode="typical")(SampleFramesStage)
    StageRegistry.register("frame_brightness", mode="typical")(FrameBrightnessStage)
    StageRegistry.register("clip_summary", mode="typical")(ClipSummaryStage)


CONFIG = PipelineConfig(
    name="video",
    version="1.0",
    dag={
        "type": "sequential",
        "name": "root",
        "children": [
            {"type": "stage", "name": "probe_videos"},
            {"type": "stage", "name": "sample_frames"},
            {"type": "stage", "name": "frame_brightness"},
            {"type": "stage", "name": "clip_summary"},
        ],
    },
    params={"sample_frames": {"every_n_frames": 5}, "clip_summary": {"cut_threshold": 0.25}},
)

# --------------------------------------------------------------------------- Y4M helpers + synthetic dataset


def read_y4m(path: Path) -> Tuple[Dict[str, Any], Iterator[bytes]]:
    """Parse a monochrome (``Cmono``) YUV4MPEG2 file: ``(header, iterator of per-frame luma bytes)``."""
    data = path.read_bytes()
    first, _, body = data.partition(b"\n")
    tokens = first.split()
    if not tokens or tokens[0] != b"YUV4MPEG2":
        raise ValueError(f"{path}: not a YUV4MPEG2 file")
    fields = {t[:1].decode(): t[1:].decode() for t in tokens[1:]}
    if fields.get("C", "mono") != "mono":
        raise ValueError(f"{path}: example reader only handles Cmono")
    num, den = (int(x) for x in fields.get("F", "25:1").split(":"))
    header = {"width": int(fields["W"]), "height": int(fields["H"]), "fps": num / den}
    size = header["width"] * header["height"]

    def frames() -> Iterator[bytes]:
        pos = 0
        while pos < len(body):
            marker_end = body.index(b"\n", pos)
            yield body[marker_end + 1 : marker_end + 1 + size]
            pos = marker_end + 1 + size

    return header, frames()


def write_y4m(path: Path, width: int, height: int, fps: int, frames: List[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = b"".join(b"FRAME\n" + frame for frame in frames)
    path.write_bytes(b"YUV4MPEG2 W%d H%d F%d:1 Ip A1:1 Cmono\n" % (width, height, fps) + body)


def build_dataset(root: Path) -> Path:
    """Write two clips: one steady shot, one with two hard cuts (dark → bright → dark)."""
    width, height, fps = 16, 12, 10
    size = width * height
    clips = {
        "v1": [bytes([140]) * size] * 20,
        "v2": [bytes([20]) * size] * 10 + [bytes([220]) * size] * 10 + [bytes([30]) * size] * 10,
    }
    rows = []
    for video_id, frames in clips.items():
        write_y4m(root / "media" / f"{video_id}.y4m", width, height, fps, frames)
        rows.append({"video_id": video_id, "media_path": f"media/{video_id}.y4m"})
    DatasetManifest(pd.DataFrame(rows), schema=SCHEMA).to_csv(manifest_csv_path(root))
    SCHEMA.to_yaml(dataset_schema_path(root))
    return root


# --------------------------------------------------------------------------- entry point


def main(workdir: Path) -> pd.DataFrame:
    register_stages()
    dataset = build_dataset(workdir / "data" / "pipeline" / "publish" / "dataset")
    result = ExperimentLauncher(workdir).run(CONFIG, "video", input_source=str(dataset))
    manifest = DatasetManifest.from_csv(manifest_csv_path(result.output_dir), schema=SCHEMA)
    print(manifest.df.to_string(index=False))
    print(f"\nRun directory: {result.output_dir}")
    return manifest.df


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="plinth-video-")))
