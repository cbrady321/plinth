
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from plinth.blocks import ParallelBlock, SequentialBlock, StageNode
from plinth.intent import StageIntent


class TestIntentValidation:
    def test_parallel_conflict_detection(self):
        # Setup mock stages with conflicting intents

        # Stage 1 writes 'col_a'
        stage1 = MagicMock()
        stage1.get_intent.return_value = StageIntent(write_columns={'col_a': 'str'})

        # Stage 2 writes 'col_a' (Conflict!)
        stage2 = MagicMock()
        stage2.get_intent.return_value = StageIntent(write_columns={'col_a': 'int'})

        # Stage 3 writes 'col_b' (No conflict)
        stage3 = MagicMock()
        stage3.get_intent.return_value = StageIntent(write_columns={'col_b': 'str'})

        # Mock StageNodes
        node1 = MagicMock(spec=StageNode)
        node1.name = "stage1"
        node1.get_written_columns.return_value = {'col_a'}
        node1.get_unique_key_modifications.return_value = set()

        node2 = MagicMock(spec=StageNode)
        node2.name = "stage2"
        node2.get_written_columns.return_value = {'col_a'}
        node2.get_unique_key_modifications.return_value = set()

        node3 = MagicMock(spec=StageNode)
        node3.name = "stage3"
        node3.get_written_columns.return_value = {'col_b'}
        node3.get_unique_key_modifications.return_value = set()

        # Test Conflict
        parallel_conflict = ParallelBlock("parallel_conflict", {}, [node1, node2])
        with pytest.raises(ValueError, match="Parallel conflict"):
            parallel_conflict.execute([], Path("/tmp"), "prefix")

        # Test Success
        parallel_ok = ParallelBlock("parallel_ok", {}, [node1, node3])
        # Mock execute on children to avoid actual execution logic
        node1.execute.return_value.output_dirs = []
        node3.execute.return_value.output_dirs = []

        # Should not raise
        parallel_ok.execute([], Path("/tmp"), "prefix")

    def test_sequential_aggregation(self):
        # Sequential block should aggregate columns from children
        node1 = MagicMock(spec=StageNode)
        node1.get_written_columns.return_value = {'col_a'}

        node2 = MagicMock(spec=StageNode)
        node2.get_written_columns.return_value = {'col_b'}

        seq = SequentialBlock("seq", {}, [node1, node2])
        assert seq.get_written_columns() == {'col_a', 'col_b'}

