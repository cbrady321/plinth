"""Refuse-not-delete cleanup tests."""

from __future__ import annotations

from pathlib import Path

from plinth.stage_directory import StageDirectoryManager


def test_strict_delete_refuses_unparseable_name(tmp_path: Path) -> None:
    experiment = tmp_path / "exp"
    experiment.mkdir()
    garbage = experiment / "not_a_valid_stage_dir"
    garbage.mkdir()
    (garbage / "keep.txt").write_text("stay")

    manager = StageDirectoryManager(experiment)
    assert manager.delete_block_directory(garbage, strict=True) is False
    assert garbage.exists()
    assert (garbage / "keep.txt").read_text() == "stay"


def test_strict_delete_refuses_outside_experiment(tmp_path: Path) -> None:
    experiment = tmp_path / "exp"
    experiment.mkdir()
    outside = tmp_path / "02_outside"
    outside.mkdir()

    manager = StageDirectoryManager(experiment)
    assert manager.delete_block_directory(outside, strict=True) is False
    assert outside.exists()


def test_strict_delete_allows_parseable_block(tmp_path: Path) -> None:
    experiment = tmp_path / "exp"
    experiment.mkdir()
    block = experiment / "06a_parallel_branch"
    block.mkdir()
    (block / "data.txt").write_text("gone")

    manager = StageDirectoryManager(experiment)
    assert manager.delete_block_directory(block, strict=True) is True
    assert not block.exists()
