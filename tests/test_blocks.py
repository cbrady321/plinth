"""Tests for DAG block execution and data flow."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plinth.blocks import (
    ExecutionConstraints,
    ParallelBlock,
    SequentialBlock,
    StageNode,
    build_dag_from_dict,
)
from plinth.context import MultiInputStageContext
from plinth.intent import StageIntent


class MockStage:
    """Mock stage for testing."""

    def __init__(self, stage_name: str, config: dict):
        self.stage_name = stage_name
        self.config = config
        self._files_processed = 0

    def prepare_context(self, context):
        return None

    def finalize_output(self, context, output_dir):
        return output_dir

    def _process_all_files(self, input_dir, output_dir, manifest):
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "output.txt"
        output_file.write_text(f"Processed by {self.stage_name}")
        self._files_processed = 1

    def get_intent(self) -> StageIntent:
        return StageIntent()


class TestBlockExecution(unittest.TestCase):
    """Test block execution and data flow."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.input_dir = self.temp_dir / "input"
        self.input_dir.mkdir()

        # Create some test input files
        (self.input_dir / "test1.bin").write_text("file data 1")
        (self.input_dir / "test2.bin").write_text("file data 2")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('plinth.blocks.StageRegistry')
    def test_sequential_block_execution(self, mock_registry):
        """Test sequential block execution chains outputs correctly."""
        # Mock stage registry
        mock_registry.get_stage.return_value = MockStage

        # Create sequential block with two stages
        config = {'params': {'stage1': {}, 'stage2': {}}}
        stage1 = StageNode('stage1', config)
        stage2 = StageNode('stage2', config)
        sequential_block = SequentialBlock('sequential', config, [stage1, stage2])

        # Execute
        output_dir = self.temp_dir / "output"
        result = sequential_block.execute([self.input_dir], output_dir, 1, parent_location_code="")

        # Verify result
        self.assertEqual(len(result.output_dirs), 1)
        self.assertEqual(result.block_name, "sequential")
        self.assertEqual(result.block_type, "sequential")

        # Verify directory structure (flat - all in output_dir)
        # Sequential block gets 01, stages get 02, 03
        self.assertTrue((output_dir / "01_sequential").exists())
        self.assertTrue((output_dir / "02_stage1").exists())
        self.assertTrue((output_dir / "03_stage2").exists())

        # Verify stage outputs
        stage1_output = output_dir / "02_stage1" / "output.txt"
        stage2_output = output_dir / "03_stage2" / "output.txt"
        self.assertTrue(stage1_output.exists())
        self.assertTrue(stage2_output.exists())
        self.assertIn("Processed by stage1", stage1_output.read_text())
        self.assertIn("Processed by stage2", stage2_output.read_text())

    @patch('plinth.blocks.StageRegistry')
    def test_parallel_block_execution(self, mock_registry):
        """Test parallel block execution with multiple outputs."""
        # Mock stage registry
        mock_registry.get_stage.return_value = MockStage

        # Create parallel block with two stages
        config = {'params': {'branch1': {}, 'branch2': {}}}
        branch1 = StageNode('branch1', config)
        branch2 = StageNode('branch2', config)
        parallel_block = ParallelBlock('parallel', config, [branch1, branch2])

        # Execute
        output_dir = self.temp_dir / "output"
        result = parallel_block.execute([self.input_dir], output_dir, 'a', parent_location_code="")

        # Verify result
        self.assertEqual(len(result.output_dirs), 1)
        self.assertEqual(result.block_name, "parallel")
        self.assertEqual(result.block_type, "parallel")

        # Verify directory structure (flat - all in output_dir)
        # Parallel block: a_parallel
        # Parallel branches (stages): a_branch1, b_branch2 (location codes)
        self.assertTrue((output_dir / "a_parallel").exists())
        self.assertTrue((output_dir / "a_branch1").exists())
        self.assertTrue((output_dir / "b_branch2").exists())

        # Verify both branches processed the same input
        branch1_output = output_dir / "a_branch1" / "output.txt"
        branch2_output = output_dir / "b_branch2" / "output.txt"
        self.assertTrue(branch1_output.exists())
        self.assertTrue(branch2_output.exists())
        self.assertIn("Processed by branch1", branch1_output.read_text())
        self.assertIn("Processed by branch2", branch2_output.read_text())

    @patch('plinth.blocks.StageRegistry')
    def test_nested_blocks(self, mock_registry):
        """Test nested block execution (sequential containing parallel)."""
        # Mock stage registry
        mock_registry.get_stage.return_value = MockStage

        # Create nested structure: sequential -> parallel -> stages
        config = {'params': {'prepare': {}, 'branch1': {}, 'branch2': {}, 'finalize': {}}}

        # Inner parallel block
        branch1 = StageNode('branch1', config)
        branch2 = StageNode('branch2', config)
        parallel_branches = ParallelBlock('branches', config, [branch1, branch2])

        # Outer sequential block
        prepare = StageNode('prepare', config)
        finalize = StageNode('finalize', config)
        sequential_block = SequentialBlock('pipeline', config, [prepare, parallel_branches, finalize])

        # Execute
        output_dir = self.temp_dir / "output"
        sequential_block.execute([self.input_dir], output_dir, 1, parent_location_code="")

        # Verify directory structure (flat - all in output_dir)
        # Sequential: 01_pipeline, 02_prepare, 03_branches (block), 04_finalize
        # Parallel branches: 03a_branch1, 03b_branch2
        assert (output_dir / "01_pipeline").exists()

        # Sequential stages
        assert (output_dir / "02_prepare").exists()
        assert (output_dir / "04_finalize").exists()

        # Parallel block and its children
        assert (output_dir / "03_branches").exists()
        assert (output_dir / "03a_branch1").exists()
        assert (output_dir / "03b_branch2").exists()

        # Verify all stages executed
        assert (output_dir / "02_prepare" / "output.txt").exists()
        assert (output_dir / "03a_branch1" / "output.txt").exists()
        assert (output_dir / "03b_branch2" / "output.txt").exists()
        assert (output_dir / "04_finalize" / "output.txt").exists()

    def test_execution_constraints(self):
        """Test execution constraints for end_at_paths."""
        constraints = ExecutionConstraints(end_index_paths=[[0, 1]])  # End at second child of first child

        # Test constraint methods
        self.assertTrue(constraints.has_any_end_paths())
        self.assertTrue(constraints.is_end_here([0, 1]))
        self.assertFalse(constraints.is_end_here([0, 0]))
        self.assertTrue(constraints.is_relevant_subtree([0]))
        self.assertFalse(constraints.is_relevant_subtree([1]))

    def test_build_dag_from_dict(self):
        """Test building DAG from dictionary representation."""
        config = {'params': {'stage1': {}, 'stage2': {}}}

        dag_dict = {
            'type': 'sequential',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'stage1'},
                {'type': 'stage', 'name': 'stage2'}
            ]
        }

        root = build_dag_from_dict(dag_dict, config)

        self.assertIsInstance(root, SequentialBlock)
        self.assertEqual(root.name, 'root')
        self.assertEqual(len(root.children), 2)
        self.assertIsInstance(root.children[0], StageNode)
        self.assertIsInstance(root.children[1], StageNode)
        self.assertEqual(root.children[0].name, 'stage1')
        self.assertEqual(root.children[1].name, 'stage2')

    def test_find_node_by_name(self):
        """Test finding nodes by name in DAG."""
        config = {'params': {'stage1': {}, 'stage2': {}}}

        # Create nested DAG
        stage1 = StageNode('stage1', config)
        stage2 = StageNode('stage2', config)
        parallel = ParallelBlock('parallel', config, [stage1, stage2])
        root = SequentialBlock('root', config, [parallel])

        # Test finding nodes
        self.assertEqual(root.find_node_by_name('root'), root)
        self.assertEqual(root.find_node_by_name('parallel'), parallel)
        self.assertEqual(root.find_node_by_name('stage1'), stage1)
        self.assertEqual(root.find_node_by_name('stage2'), stage2)
        self.assertIsNone(root.find_node_by_name('nonexistent'))

    def test_find_node_by_path(self):
        """Test finding nodes by index path."""
        config = {'params': {'stage1': {}, 'stage2': {}}}

        # Create nested DAG
        stage1 = StageNode('stage1', config)
        stage2 = StageNode('stage2', config)
        parallel = ParallelBlock('parallel', config, [stage1, stage2])
        root = SequentialBlock('root', config, [parallel])

        # Test finding by path
        self.assertEqual(root.find_node_by_path([]), root)
        self.assertEqual(root.find_node_by_path([0]), parallel)
        self.assertEqual(root.find_node_by_path([0, 0]), stage1)
        self.assertEqual(root.find_node_by_path([0, 1]), stage2)
        self.assertIsNone(root.find_node_by_path([1]))  # Out of bounds
        self.assertIsNone(root.find_node_by_path([0, 2]))  # Out of bounds


class TestExecutionConstraints(unittest.TestCase):
    """Test execution constraints functionality."""

    def test_empty_constraints(self):
        """Test constraints with no end paths."""
        constraints = ExecutionConstraints()
        self.assertFalse(constraints.has_any_end_paths())
        self.assertFalse(constraints.is_end_here([0, 1]))
        self.assertFalse(constraints.is_relevant_subtree([0]))

    def test_single_end_path(self):
        """Test constraints with single end path."""
        constraints = ExecutionConstraints(end_index_paths=[[0, 1]])

        self.assertTrue(constraints.has_any_end_paths())
        self.assertTrue(constraints.is_end_here([0, 1]))
        self.assertFalse(constraints.is_end_here([0, 0]))
        self.assertFalse(constraints.is_end_here([1, 1]))

        # Test subtree relevance
        self.assertTrue(constraints.is_relevant_subtree([0]))  # Ancestor
        self.assertTrue(constraints.is_relevant_subtree([0, 1]))  # Exact match
        self.assertFalse(constraints.is_relevant_subtree([1]))  # Sibling
        self.assertFalse(constraints.is_relevant_subtree([0, 1, 2]))  # Descendant

    def test_multiple_end_paths(self):
        """Test constraints with multiple end paths."""
        constraints = ExecutionConstraints(end_index_paths=[[0, 1], [0, 2], [1, 0]])

        self.assertTrue(constraints.has_any_end_paths())
        self.assertTrue(constraints.is_end_here([0, 1]))
        self.assertTrue(constraints.is_end_here([0, 2]))
        self.assertTrue(constraints.is_end_here([1, 0]))
        self.assertFalse(constraints.is_end_here([0, 0]))

        # Test subtree relevance
        self.assertTrue(constraints.is_relevant_subtree([0]))  # Ancestor of [0,1] and [0,2]
        self.assertTrue(constraints.is_relevant_subtree([1]))  # Ancestor of [1,0]
        self.assertFalse(constraints.is_relevant_subtree([2]))  # No descendants


class TestNestedBlockExecution(unittest.TestCase):
    """Test nested block execution scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.input_dir = self.temp_dir / "input"
        self.input_dir.mkdir()
        (self.input_dir / "test.bin").write_text("file data")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('plinth.blocks.StageRegistry')
    def test_sequential_containing_parallel(self, mock_registry):
        """Test sequential block containing parallel block."""
        mock_registry.get_stage.return_value = MockStage

        # Create nested structure: sequential -> parallel -> stages
        config = {'params': {'stage1': {}, 'stage2': {}, 'stage3': {}}}

        # Inner parallel block
        parallel_stage1 = StageNode('stage1', config)
        parallel_stage2 = StageNode('stage2', config)
        parallel_block = ParallelBlock('parallel', config, [parallel_stage1, parallel_stage2])

        # Outer sequential block
        sequential_stage = StageNode('stage3', config)
        sequential_block = SequentialBlock('sequential', config, [parallel_block, sequential_stage])

        # Execute
        output_dir = self.temp_dir / "output"
        sequential_block.execute([self.input_dir], output_dir, 1, parent_location_code="")

        # Verify structure (flat - all in output_dir)
        # Sequential: 01_sequential, 02_parallel (block), 03_stage3
        # Parallel branches: 02a_stage1, 02b_stage2
        assert (output_dir / "01_sequential").exists()

        # Parallel block directory
        assert (output_dir / "02_parallel").exists()
        assert (output_dir / "02a_stage1").exists()
        assert (output_dir / "02b_stage2").exists()

        # Sequential stage directory
        assert (output_dir / "03_stage3").exists()

        # Verify all stages executed
        assert (output_dir / "02a_stage1" / "output.txt").exists()
        assert (output_dir / "02b_stage2" / "output.txt").exists()
        assert (output_dir / "03_stage3" / "output.txt").exists()

    @patch('plinth.blocks.StageRegistry')
    def test_parallel_containing_sequential(self, mock_registry):
        """Test parallel block containing sequential blocks."""
        mock_registry.get_stage.return_value = MockStage

        # Create nested structure: parallel -> sequential -> stages
        config = {'params': {'stage1': {}, 'stage2': {}, 'stage3': {}, 'stage4': {}}}

        # Inner sequential blocks
        seq1_stage1 = StageNode('stage1', config)
        seq1_stage2 = StageNode('stage2', config)
        sequential_block1 = SequentialBlock('sequential1', config, [seq1_stage1, seq1_stage2])

        seq2_stage3 = StageNode('stage3', config)
        seq2_stage4 = StageNode('stage4', config)
        sequential_block2 = SequentialBlock('sequential2', config, [seq2_stage3, seq2_stage4])

        # Outer parallel block
        parallel_block = ParallelBlock('parallel', config, [sequential_block1, sequential_block2])

        # Execute
        output_dir = self.temp_dir / "output"
        parallel_block.execute([self.input_dir], output_dir, 'a', parent_location_code="")

        # Verify structure (flat - all in output_dir)
        # Parallel: a_parallel (block), a_sequential1 (block), b_sequential2 (block)
        # Sequential stages within parallel branches use location codes: a01_stage1, a02_stage2, b01_stage3, b02_stage4
        assert (output_dir / "a_parallel").exists()

        # Sequential block directories (children of parallel block) - use location codes
        assert (output_dir / "a_sequential1").exists()
        assert (output_dir / "b_sequential2").exists()

        # Stage directories within sequential blocks (location codes within parallel branches)
        assert (output_dir / "a01_stage1").exists()
        assert (output_dir / "a02_stage2").exists()
        assert (output_dir / "b01_stage3").exists()
        assert (output_dir / "b02_stage4").exists()

        # Verify all stages executed
        assert (output_dir / "a01_stage1" / "output.txt").exists()
        assert (output_dir / "a02_stage2" / "output.txt").exists()
        assert (output_dir / "b01_stage3" / "output.txt").exists()
        assert (output_dir / "b02_stage4" / "output.txt").exists()


class TestErrorHandling(unittest.TestCase):
    """Test error handling in block execution."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.input_dir = self.temp_dir / "input"
        self.input_dir.mkdir()
        (self.input_dir / "test.bin").write_text("file data")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('plinth.blocks.StageRegistry')
    def test_parallel_block_fail_fast(self, mock_registry):
        """Test parallel block with fail_fast error policy."""
        mock_registry.get_stage.return_value = MockStage

        # Create parallel block with one failing stage
        config = {
            'params': {'stage1': {}, 'stage2': {}},
            'parallel_error_policy': 'fail_fast'
        }

        # Mock one stage to fail
        class FailingMockStage:
            def __init__(self, stage_name, config):
                self.stage_name = stage_name
                self.config = config
                self._files_processed = 0

            def prepare_context(self, context):
                return None

            def finalize_output(self, context, output_dir):
                return output_dir

            def get_intent(self):
                return StageIntent()

            def _process_all_files(self, input_dir, output_dir, manifest):
                if self.stage_name == 'stage2':
                    raise RuntimeError("Stage 2 failed")
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "output.txt").write_text(f"Processed by {self.stage_name}")
                self._files_processed = 1

        with patch('plinth.blocks.StageRegistry.get_stage', return_value=FailingMockStage):
            stage1 = StageNode('stage1', config)
            stage2 = StageNode('stage2', config)
            parallel_block = ParallelBlock('parallel', config, [stage1, stage2])

            # Should raise exception due to fail_fast policy
            with self.assertRaisesRegex(RuntimeError, "Stage 2 failed"):
                parallel_block.execute([self.input_dir], self.temp_dir / "output", 'a', parent_location_code="")

    @patch('plinth.blocks.StageRegistry')
    def test_parallel_block_continue(self, mock_registry):
        """Test parallel block with continue error policy."""
        mock_registry.get_stage.return_value = MockStage

        # Create parallel block with one failing stage
        config = {
            'params': {'stage1': {}, 'stage2': {}},
            'parallel_error_policy': 'continue'
        }

        # Mock one stage to fail
        class FailingMockStage:
            def __init__(self, stage_name, config):
                self.stage_name = stage_name
                self.config = config
                self._files_processed = 0

            def prepare_context(self, context):
                return None

            def finalize_output(self, context, output_dir):
                return output_dir

            def get_intent(self):
                return StageIntent()

            def _process_all_files(self, input_dir, output_dir, manifest):
                if self.stage_name == 'stage2':
                    raise RuntimeError("Stage 2 failed")
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "output.txt").write_text(f"Processed by {self.stage_name}")
                self._files_processed = 1

        with patch('plinth.blocks.StageRegistry.get_stage', return_value=FailingMockStage):
            stage1 = StageNode('stage1', config)
            stage2 = StageNode('stage2', config)
            parallel_block = ParallelBlock('parallel', config, [stage1, stage2])

            # Should not raise exception, should continue with other branches
            parallel_block.execute([self.input_dir], self.temp_dir / "output", 'a', parent_location_code="")

            # Verify successful branch output exists (flat structure)
            output_dir = self.temp_dir / "output"
            # Parallel branches: a_stage1, b_stage2 (location codes)
            self.assertTrue((output_dir / "a_stage1" / "output.txt").exists())
            # stage2 directory should exist (created before execution) but be empty due to failure
            self.assertTrue((output_dir / "b_stage2").exists())
            # But no output file should exist since stage failed
            self.assertFalse((output_dir / "b_stage2" / "output.txt").exists())


class TestBuildDAGFromDict(unittest.TestCase):
    """Test build_dag_from_dict function."""

    def test_simple_sequential_dag(self):
        """Test building simple sequential DAG."""
        config = {'params': {'stage1': {}, 'stage2': {}}}

        dag_dict = {
            'type': 'sequential',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'stage1'},
                {'type': 'stage', 'name': 'stage2'}
            ]
        }

        root = build_dag_from_dict(dag_dict, config)

        self.assertIsInstance(root, SequentialBlock)
        self.assertEqual(root.name, 'root')
        self.assertEqual(len(root.children), 2)
        self.assertIsInstance(root.children[0], StageNode)
        self.assertIsInstance(root.children[1], StageNode)
        self.assertEqual(root.children[0].name, 'stage1')
        self.assertEqual(root.children[1].name, 'stage2')

    def test_simple_parallel_dag(self):
        """Test building simple parallel DAG."""
        config = {'params': {'stage1': {}, 'stage2': {}}}

        dag_dict = {
            'type': 'parallel',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'stage1'},
                {'type': 'stage', 'name': 'stage2'}
            ]
        }

        root = build_dag_from_dict(dag_dict, config)

        self.assertIsInstance(root, ParallelBlock)
        self.assertEqual(root.name, 'root')
        self.assertEqual(len(root.children), 2)
        self.assertIsInstance(root.children[0], StageNode)
        self.assertIsInstance(root.children[1], StageNode)
        self.assertEqual(root.children[0].name, 'stage1')
        self.assertEqual(root.children[1].name, 'stage2')

    def test_deeply_nested_dag(self):
        """Test building deeply nested DAG (4+ levels)."""
        config = {'params': {'stage1': {}, 'stage2': {}, 'stage3': {}, 'stage4': {}}}

        dag_dict = {
            'type': 'sequential',
            'name': 'level1',
            'children': [
                {
                    'type': 'parallel',
                    'name': 'level2',
                    'children': [
                        {
                            'type': 'sequential',
                            'name': 'level3',
                            'children': [
                                {
                                    'type': 'parallel',
                                    'name': 'level4',
                                    'children': [
                                        {'type': 'stage', 'name': 'stage1'},
                                        {'type': 'stage', 'name': 'stage2'}
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {'type': 'stage', 'name': 'stage3'},
                {'type': 'stage', 'name': 'stage4'}
            ]
        }

        root = build_dag_from_dict(dag_dict, config)

        # Verify structure
        self.assertIsInstance(root, SequentialBlock)
        self.assertEqual(root.name, 'level1')
        self.assertEqual(len(root.children), 3)

        # Check level 2 (parallel)
        level2 = root.children[0]
        self.assertIsInstance(level2, ParallelBlock)
        self.assertEqual(level2.name, 'level2')

        # Check level 3 (sequential)
        level3 = level2.children[0]
        self.assertIsInstance(level3, SequentialBlock)
        self.assertEqual(level3.name, 'level3')

        # Check level 4 (parallel)
        level4 = level3.children[0]
        self.assertIsInstance(level4, ParallelBlock)
        self.assertEqual(level4.name, 'level4')
        self.assertEqual(len(level4.children), 2)

        # Check stages
        self.assertIsInstance(level4.children[0], StageNode)
        self.assertIsInstance(level4.children[1], StageNode)
        self.assertIsInstance(root.children[1], StageNode)
        self.assertIsInstance(root.children[2], StageNode)

    def test_invalid_block_type(self):
        """Test error handling with invalid block type."""
        config = {'params': {}}

        dag_dict = {
            'type': 'invalid_type',
            'name': 'root',
            'children': []
        }

        with self.assertRaisesRegex(ValueError, "Unknown block type: invalid_type"):
            build_dag_from_dict(dag_dict, config)

    def test_missing_required_fields(self):
        """Test error handling with missing required fields."""
        config = {'params': {}}

        # Missing 'type' field
        dag_dict = {
            'name': 'root',
            'children': []
        }

        with self.assertRaisesRegex(ValueError, "dag: missing 'type'"):
            build_dag_from_dict(dag_dict, config)

        # Missing 'name' field
        dag_dict = {
            'type': 'sequential',
            'children': []
        }

        with self.assertRaisesRegex(ValueError, "dag: sequential block is missing a 'name'"):
            build_dag_from_dict(dag_dict, config)


class TestMultiInputContext(unittest.TestCase):
    """Test multi-input context functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.input1 = self.temp_dir / "input1"
        self.input2 = self.temp_dir / "input2"
        self.output = self.temp_dir / "output"

        # Create input directories with test files
        self.input1.mkdir()
        self.input2.mkdir()
        (self.input1 / "file1.bin").write_text("file 1")
        (self.input2 / "file2.bin").write_text("file 2")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_input_context(self):
        """Test multi-input context functionality."""
        context = MultiInputStageContext([self.input1, self.input2], self.output)

        # Test basic properties
        self.assertEqual(context.get_input_dir(), self.input1)  # First input as primary
        self.assertEqual(context.get_input_dirs(), [self.input1, self.input2])
        self.assertEqual(context.get_output_dir(), self.output)

        # Test that files from both inputs are accessible
        input_dirs = context.get_input_dirs()
        all_files = []
        for input_dir in input_dirs:
            all_files.extend(list(input_dir.glob("*.bin")))

        self.assertEqual(len(all_files), 2)
        self.assertTrue(any("file1.bin" in str(f)) for f in all_files)
        self.assertTrue(any("file2.bin" in str(f)) for f in all_files)
