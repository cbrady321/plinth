"""Every script in ``examples/`` runs end to end and produces the documented result.

The examples are the proof that nothing in plinth assumes a data type: tabular rows with no
files, text, images, audio and video all go through the same runtime.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted(p.stem for p in (ROOT / "examples").glob("*.py"))


def _run(name: str, tmp_path: Path):
    return importlib.import_module(f"examples.{name}").main(tmp_path)


def test_every_example_is_covered() -> None:
    assert EXAMPLES == ["audio_tracks", "images", "tabular_records", "text_documents", "video"]


@pytest.mark.usefixtures("isolated_registry")
def test_tabular_records(tmp_path: Path) -> None:
    df = _run("tabular_records", tmp_path)
    assert df.set_index("customer_id")[["order_count", "revenue"]].to_dict("index") == {
        "c1": {"order_count": 2, "revenue": 75.0},
        "c2": {"order_count": 1, "revenue": 15.0},
    }
    run_dir = tmp_path / "data" / "pipeline" / "runs" / "tabular_records"
    assert not [p for p in run_dir.rglob("*") if p.is_file() and p.suffix not in {".csv", ".yaml"}]


@pytest.mark.usefixtures("isolated_registry")
def test_text_documents(tmp_path: Path) -> None:
    df = _run("text_documents", tmp_path)
    assert df.set_index("doc_id")[["paragraph_count", "total_words"]].to_dict("index") == {
        "d1": {"paragraph_count": 2, "total_words": 24},
        "d2": {"paragraph_count": 2, "total_words": 20},
    }
    paragraphs = sorted(p.name for p in (tmp_path / "data").rglob("*_p0*.txt"))
    assert paragraphs == ["d1_p001.txt", "d1_p002.txt", "d1_p003.txt", "d2_p001.txt", "d2_p002.txt"]


@pytest.mark.usefixtures("isolated_registry")
def test_images(tmp_path: Path) -> None:
    df = _run("images", tmp_path).set_index("image_id")
    assert sorted(df.index) == ["i1", "i2", "i3"]
    assert df.loc["i1", ["thumb_width", "thumb_height"]].tolist() == [16, 12]
    for path in df["image_path"]:
        assert "make_thumbnails" in path and Path(path).exists()
    report = next((tmp_path / "data").rglob("camera_report.csv")).read_text().splitlines()
    assert report == ["camera,image_count,mean_brightness", "north,2,0.6036", "south,1,0.5098"]


@pytest.mark.usefixtures("isolated_registry")
def test_audio_tracks(tmp_path: Path) -> None:
    df = _run("audio_tracks", tmp_path)
    assert df.set_index("album")[["track_count", "total_duration_s"]].to_dict("index") == {
        "dawn": {"track_count": 2, "total_duration_s": 1.8},
        "dusk": {"track_count": 1, "total_duration_s": 1.2},
    }
    normalized = sorted(p.name for p in (tmp_path / "data" / "pipeline" / "runs").rglob("*.wav"))
    assert normalized == ["t1.wav", "t2.wav", "t3.wav"]


@pytest.mark.usefixtures("isolated_registry")
def test_video(tmp_path: Path) -> None:
    df = _run("video", tmp_path).set_index("video_id")
    assert df.loc["v1", ["sampled_frames", "cut_count"]].tolist() == [4, 0]
    assert df.loc["v2", ["sampled_frames", "cut_count"]].tolist() == [6, 2]
    assert len(list((tmp_path / "data" / "pipeline" / "runs").rglob("*.pgm"))) == 10
