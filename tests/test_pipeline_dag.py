"""Tests for DAG pipeline execution and JSONPath functionality."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from plinth.config import PipelineConfig
from plinth.jsonpath_resolver import expand_jsonpath_indices, path_to_index_list
from plinth.runtime.pipeline import Pipeline
from plinth.stage_directory import StageDirectoryManager


class TestJSONPathResolver(unittest.TestCase):
    """Test JSONPath resolution functionality."""

    def test_expand_jsonpath_indices(self):
        """Test expanding comma-separated indices in JSONPath."""
        # Simple case
        paths = expand_jsonpath_indices("$.root.children[1].children[0]")
        self.assertEqual(paths, ["$.root.children[1].children[0]"])

        # Comma-separated indices
        paths = expand_jsonpath_indices("$.root.children[1].children[0,2]")
        self.assertEqual(paths, ["$.root.children[1].children[0]", "$.root.children[1].children[2]"])

        # Multiple comma-separated indices
        paths = expand_jsonpath_indices("$.root.children[0,1].children[0,2]")
        expected = [
            "$.root.children[0].children[0]",
            "$.root.children[0].children[2]",
            "$.root.children[1].children[0]",
            "$.root.children[1].children[2]"
        ]
        self.assertEqual(set(paths), set(expected))

    def test_path_to_index_list(self):
        """Test converting JSONPath to index list."""
        # Simple path
        indices = path_to_index_list("$.root.children[1].children[0]", "root")
        self.assertEqual(indices, [1, 0])

        # Longer path
        indices = path_to_index_list("$.root.children[0].children[1].children[2]", "root")
        self.assertEqual(indices, [0, 1, 2])

        # Invalid root name
        with self.assertRaises(ValueError):
            path_to_index_list("$.wrong.children[0]", "root")


class TestPipelineDAG(unittest.TestCase):
    """Test DAG pipeline execution."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_root = self.temp_dir / "project"
        self.data_root = self.project_root / "data"
        self.dataset_dir = self.data_root / "dataset"
        self.raw_dir = self.data_root / "raw"

        # Create directory structure
        self.dataset_dir.mkdir(parents=True)
        (self.dataset_dir / "test.bin").write_text("test data")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('plinth.blocks.StageRegistry')
    def test_simple_sequential_dag(self, mock_registry):
        """Test simple sequential DAG execution."""
        # Mock stage registry
        mock_registry.get_stage.return_value = Mock

        # Create simple sequential DAG
        dag = {
            'type': 'sequential',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'prepare'},
                {'type': 'stage', 'name': 'finalize'}
            ]
        }

        config = PipelineConfig(
            name="test_pipeline",
            version="1.0",
            dag=dag,
            params={
                'prepare': {'param1': 'value1'},
                'finalize': {'param2': 'value2'}
            }
        )

        pipeline = Pipeline(config, "test_experiment", self.project_root)

        # Verify DAG was built correctly
        self.assertIsNotNone(pipeline._dag_root)
        self.assertEqual(pipeline._dag_root.name, 'root')
        self.assertEqual(len(pipeline._dag_root.children), 2)

    @patch('plinth.blocks.StageRegistry')
    def test_parallel_dag_execution(self, mock_registry):
        """Test parallel DAG execution."""
        # Mock stage registry
        mock_registry.get_stage.return_value = Mock

        # Create parallel DAG
        dag = {
            'type': 'parallel',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'branch1'},
                {'type': 'stage', 'name': 'branch2'},
                {'type': 'stage', 'name': 'branch3'}
            ]
        }

        config = PipelineConfig(
            name="test_pipeline",
            version="1.0",
            dag=dag,
            params={
                'branch1': {},
                'branch2': {},
                'branch3': {}
            }
        )

        pipeline = Pipeline(config, "test_experiment", self.project_root)

        # Verify DAG structure
        self.assertEqual(pipeline._dag_root.name, 'root')
        self.assertEqual(len(pipeline._dag_root.children), 3)
        self.assertTrue(all(child.name in ['branch1', 'branch2', 'branch3'] for child in pipeline._dag_root.children))

    @patch('plinth.blocks.StageRegistry')
    def test_nested_dag_execution(self, mock_registry):
        """Test nested DAG execution (sequential containing parallel)."""
        # Mock stage registry
        mock_registry.get_stage.return_value = Mock

        # Create nested DAG
        dag = {
            'type': 'sequential',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'prepare'},
                {
                    'type': 'parallel',
                    'name': 'branches',
                    'children': [
                        {'type': 'stage', 'name': 'branch_a'},
                        {'type': 'stage', 'name': 'branch_b'}
                    ]
                },
                {'type': 'stage', 'name': 'finalize'}
            ]
        }

        config = PipelineConfig(
            name="test_pipeline",
            version="1.0",
            dag=dag,
            params={
                'prepare': {},
                'branch_a': {},
                'branch_b': {},
                'finalize': {}
            }
        )

        pipeline = Pipeline(config, "test_experiment", self.project_root)

        # Verify nested structure
        root = pipeline._dag_root
        self.assertEqual(root.name, 'root')
        self.assertEqual(len(root.children), 3)

        # Check prepare stage
        prepare = root.children[0]
        self.assertEqual(prepare.name, 'prepare')

        # Check parallel branches block
        branches = root.children[1]
        self.assertEqual(branches.name, 'branches')
        self.assertEqual(len(branches.children), 2)
        self.assertTrue(all(child.name in ['branch_a', 'branch_b'] for child in branches.children))

        # Check finalize stage
        finalize = root.children[2]
        self.assertEqual(finalize.name, 'finalize')

    def test_jsonpath_cleanup(self):
        """Test JSONPath-based cleanup functionality."""
        # Create a mock DAG structure for testing cleanup
        dag = {
            'type': 'sequential',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'stage1'},
                {
                    'type': 'parallel',
                    'name': 'parallel_block',
                    'children': [
                        {'type': 'stage', 'name': 'branch1'},
                        {'type': 'stage', 'name': 'branch2'},
                        {'type': 'stage', 'name': 'branch3'}
                    ]
                },
                {'type': 'stage', 'name': 'stage2'}
            ]
        }

        config = PipelineConfig(
            name="test_pipeline",
            version="1.0",
            dag=dag,
            params={}
        )

        Pipeline(config, "test_experiment", self.project_root)

        # Test cleanup from specific parallel branches
        jsonpaths = ["$.root.children[1].children[0,2]"]  # branch1 and branch3
        expanded = []
        for path in jsonpaths:
            expanded.extend(expand_jsonpath_indices(path))

        self.assertEqual(len(expanded), 2)
        assert "$.root.children[1].children[0]" in expanded
        assert "$.root.children[1].children[2]" in expanded

        # Convert to index lists
        index_lists = []
        for path in expanded:
            index_lists.append(path_to_index_list(path, "root"))

        assert [1, 0] in index_lists
        assert [1, 2] in index_lists


class TestStageDirectoryManager(unittest.TestCase):
    """Test enhanced StageDirectoryManager with DAG support."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.experiment_dir = self.temp_dir / "experiment"
        self.experiment_dir.mkdir()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_alpha_prefix_detection(self):
        """Test detection of alpha-prefixed directories."""
        (self.experiment_dir / "a_left").mkdir()
        (self.experiment_dir / "b_middle").mkdir()
        (self.experiment_dir / "c_right").mkdir()

        manager = StageDirectoryManager(self.experiment_dir)

        block_dirs = manager.block_directories
        self.assertEqual(len(block_dirs), 3)

        # Verify they're detected as parallel blocks
        parallel_blocks = [bd for bd in block_dirs if bd.is_parallel]
        self.assertEqual(len(parallel_blocks), 3)

        # Check location codes
        location_codes = [bd.location_code for bd in parallel_blocks]
        assert 'a' in location_codes
        assert 'b' in location_codes
        assert 'c' in location_codes

    def test_mixed_directory_types(self):
        """Test detection of mixed directory types (numbered and alpha)."""
        # numbered and lettered directories side by side
        (self.experiment_dir / "01_stage1").mkdir()  # numbered stage
        (self.experiment_dir / "02_stage2").mkdir()  # numbered stage
        (self.experiment_dir / "a_parallel1").mkdir()  # Parallel block
        (self.experiment_dir / "b_parallel2").mkdir()  # Parallel block
        (self.experiment_dir / "03_block1").mkdir()  # numbered block, parsed like a stage

        manager = StageDirectoryManager(self.experiment_dir)

        # Numbered directories are stage directories
        stage_dirs = manager.stage_directories
        self.assertEqual(len(stage_dirs), 3)
        self.assertTrue(any(sd.stage_name == 'stage1' for sd in stage_dirs))
        self.assertTrue(any(sd.stage_name == 'stage2' for sd in stage_dirs))
        self.assertTrue(any(sd.stage_name == 'block1' for sd in stage_dirs))

        block_dirs = manager.block_directories
        self.assertEqual(len(block_dirs), 2)

        # Check parallel blocks
        parallel_blocks = [bd for bd in block_dirs if bd.is_parallel]
        self.assertEqual(len(parallel_blocks), 2)

    def test_parallel_outputs_discovery(self):
        """Test discovery of parallel outputs within a block."""
        # a block whose lettered children are branch outputs
        block_dir = self.experiment_dir / "01_parallel_block"
        block_dir.mkdir()

        (block_dir / "a_left").mkdir()
        (block_dir / "b_middle").mkdir()
        (block_dir / "c_right").mkdir()

        (block_dir / "other_dir").mkdir()
        (block_dir / "01_sequential").mkdir()

        manager = StageDirectoryManager(self.experiment_dir)

        parallel_outputs = manager.get_parallel_outputs(block_dir)
        self.assertEqual(len(parallel_outputs), 3)

        output_names = [p.name for p in parallel_outputs]
        assert 'a_left' in output_names
        assert 'b_middle' in output_names
        assert 'c_right' in output_names

    def test_block_directory_creation(self):
        """Test creation of block directories."""
        manager = StageDirectoryManager(self.experiment_dir)

        # Create sequential block
        seq_block = manager.create_block_directory("sequential_block", is_parallel=False, location_code="01")
        self.assertEqual(seq_block.block_name, "sequential_block")
        self.assertFalse(seq_block.is_parallel)
        self.assertEqual(seq_block.location_code, "01")
        assert (self.experiment_dir / "01_sequential_block").exists()

        # Create parallel blocks
        par_block1 = manager.create_block_directory("parallel_block1", is_parallel=True, location_code="06a")
        self.assertEqual(par_block1.block_name, "parallel_block1")
        self.assertTrue(par_block1.is_parallel)
        self.assertEqual(par_block1.location_code, "06a")
        assert (self.experiment_dir / "06a_parallel_block1").exists()

        par_block2 = manager.create_block_directory("parallel_block2", is_parallel=True, location_code="06b")
        self.assertEqual(par_block2.location_code, "06b")
        assert (self.experiment_dir / "06b_parallel_block2").exists()

    def test_block_directory_deletion(self):
        """Test deletion of block directories."""
        # Create a block directory with contents
        block_dir = self.experiment_dir / "01_test_block"
        block_dir.mkdir()
        (block_dir / "subdir").mkdir()
        (block_dir / "test_file.txt").write_text("test content")

        manager = StageDirectoryManager(self.experiment_dir)

        success = manager.delete_block_directory(block_dir)
        self.assertTrue(success)
        self.assertFalse(block_dir.exists())

        # Verify it's removed from the manager's list
        self.assertEqual(len(manager.block_directories), 0)
