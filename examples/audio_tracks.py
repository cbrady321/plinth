"""Audio: probe, loudness-normalize and summarize a music library.

Each manifest row is one track (a WAV file), identified by ``album`` and ``track``. The pipeline

1. ``probe_tracks``      reads every file's header (sample rate, channels, duration),
2. ``drop_short_tracks`` filters out tracks shorter than ``min_seconds``,
3. ``normalize_peak``    rewrites each track so its peak hits ``target_peak`` (new files),
4. ``album_summary``     collapses tracks into one row per album.

Run it::

    python examples/audio_tracks.py [workdir]

Only the standard library is used to read and write audio so the example runs anywhere; in a real
project swap in ``soundfile``, ``librosa``, ``pydub``, … inside the stage bodies — Plinth never sees
the decoder, only the manifest rows and file paths.
"""

from __future__ import annotations

import array
import math
import sys
import tempfile
import wave
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
    identity=ManifestIdentity(entity_key="album", hierarchy_keys=["track"]),
    media=MediaSpec(path_column="track_path", subdir="tracks"),
)

# --------------------------------------------------------------------------- stages


class ProbeTracksStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"track_path"},
            write_columns={"sample_rate": "int", "channels": "int", "duration_s": "float"},
            reads_files=True,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        with wave.open(str(input_path), "rb") as wav:
            rate = wav.getframerate()
            return StageOutcome.update(
                sample_rate=rate,
                channels=wav.getnchannels(),
                duration_s=round(wav.getnframes() / rate, 3),
            )


class DropShortTracksStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"duration_s"},
            filters_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        if float(metadata["duration_s"]) < float(self.config.get("min_seconds", 0)):
            return StageOutcome.filter()
        return StageOutcome.update()


class NormalizePeakStage(BaseStage):
    """Writes a gain-adjusted copy of every track; the engine records the new file location."""

    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"track_path"},
            write_columns={"gain": "float"},
            reads_files=True,
            modifies_files=True,
        )

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        params, samples = _read_pcm16(input_path)
        peak = max((abs(s) for s in samples), default=0)
        gain = (float(self.config.get("target_peak", 0.9)) * 32767 / peak) if peak else 1.0
        scaled = array.array("h", (max(-32768, min(32767, round(s * gain))) for s in samples))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_pcm16(output_path, params.framerate, params.nchannels, scaled)
        return StageOutcome.update(gain=round(gain, 4))


class AlbumSummaryStage(BaseStage):
    def get_intent(self) -> StageIntent:
        return StageIntent(
            required_input_columns={"album", "duration_s"},
            write_columns={"track_count": "int", "total_duration_s": "float"},
            group_by=["album"],
            aggregates_rows=True,
            reads_files=False,
            modifies_files=False,
        )

    def process_group(
        self, group_keys: Dict[str, Any], rows: List[Dict[str, Any]], input_dir: Path, output_dir: Path
    ) -> StageOutcome:
        return StageOutcome.aggregate(
            album=group_keys["album"],
            track_count=len(rows),
            total_duration_s=round(sum(float(r["duration_s"]) for r in rows), 3),
        )


def register_stages() -> None:
    StageRegistry.register("probe_tracks", mode="typical")(ProbeTracksStage)
    StageRegistry.register("drop_short_tracks", mode="typical")(DropShortTracksStage)
    StageRegistry.register("normalize_peak", mode="typical")(NormalizePeakStage)
    StageRegistry.register("album_summary", mode="typical")(AlbumSummaryStage)


CONFIG = PipelineConfig(
    name="audio_tracks",
    version="1.0",
    dag={
        "type": "sequential",
        "name": "root",
        "children": [
            {"type": "stage", "name": "probe_tracks"},
            {"type": "stage", "name": "drop_short_tracks"},
            {"type": "stage", "name": "normalize_peak"},
            {"type": "stage", "name": "album_summary"},
        ],
    },
    params={"drop_short_tracks": {"min_seconds": 0.5}, "normalize_peak": {"target_peak": 0.9}},
)

# --------------------------------------------------------------------------- synthetic dataset


def build_dataset(root: Path) -> Path:
    """Write four short WAV tracks across two albums, plus ``manifest.csv`` and ``dataset_schema.yaml``."""
    tracks = [
        ("t1", "dawn", 440.0, 1.0, 0.30),
        ("t2", "dawn", 660.0, 0.8, 0.50),
        ("t3", "dusk", 330.0, 1.2, 0.20),
        ("t4", "dusk", 550.0, 0.2, 0.40),  # too short: filtered out
    ]
    rows = []
    for track, album, freq, seconds, amplitude in tracks:
        rate = 8000
        tone = (amplitude * 32767 * math.sin(2 * math.pi * freq * n / rate) for n in range(int(rate * seconds)))
        _write_pcm16(root / "tracks" / f"{track}.wav", rate, 1, array.array("h", (round(s) for s in tone)))
        rows.append({"album": album, "track": track, "track_path": f"tracks/{track}.wav"})
    DatasetManifest(pd.DataFrame(rows), schema=SCHEMA).to_csv(manifest_csv_path(root))
    SCHEMA.to_yaml(dataset_schema_path(root))
    return root


def _read_pcm16(path: Path) -> tuple[Any, array.array]:
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        samples = array.array("h")
        samples.frombytes(wav.readframes(params.nframes))
    return params, samples


def _write_pcm16(path: Path, rate: int, channels: int, samples: array.array) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())


# --------------------------------------------------------------------------- entry point


def main(workdir: Path) -> pd.DataFrame:
    register_stages()
    dataset = build_dataset(workdir / "data" / "pipeline" / "publish" / "dataset")
    result = ExperimentLauncher(workdir).run(CONFIG, "audio_tracks", input_source=str(dataset))
    manifest = DatasetManifest.from_csv(manifest_csv_path(result.output_dir), schema=SCHEMA)
    print(manifest.df.to_string(index=False))
    print(f"\nRun directory: {result.output_dir}")
    return manifest.df


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="plinth-audio-")))
