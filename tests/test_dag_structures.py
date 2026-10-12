"""Tests for DAG dataclasses and convenience functions."""

import unittest
from unittest.mock import Mock, patch

from plinth.dag_structures import (
    DAGConfig,
    ParallelBlockConfig,
    SequentialBlockConfig,
    StageConfig,
    create_fan_out_pipeline,
    create_nested_parallel_pipeline,
    create_simple_sequential_pipeline,
)


class TestDAGDataclasses(unittest.TestCase):
    """Test DAG dataclass functionality."""

    def test_stage_config(self):
        """Test StageConfig dataclass."""
        stage = StageConfig("test_stage", {"param1": "value1"})

        self.assertEqual(stage.name, "test_stage")
        self.assertEqual(stage.params, {"param1": "value1"})

        # Test to_dict conversion
        stage_dict = stage.to_dict()
        self.assertEqual(stage_dict, {
            'type': 'stage',
            'name': 'test_stage'
        })

    def test_stage_config_default_params(self):
        """Test StageConfig with default params (empty dict)."""
        stage = StageConfig("test_stage")

        self.assertEqual(stage.name, "test_stage")
        self.assertEqual(stage.params, {})

        # Test to_dict conversion
        stage_dict = stage.to_dict()
        self.assertEqual(stage_dict, {
            'type': 'stage',
            'name': 'test_stage'
        })

    def test_sequential_block_config(self):
        """Test SequentialBlockConfig dataclass."""
        stage1 = StageConfig("stage1")
        stage2 = StageConfig("stage2")

        block = SequentialBlockConfig("sequential_block", [stage1, stage2])

        self.assertEqual(block.name, "sequential_block")
        self.assertEqual(len(block.children), 2)
        self.assertEqual(block.children[0].name, "stage1")
        self.assertEqual(block.children[1].name, "stage2")

        # Test to_dict conversion
        block_dict = block.to_dict()
        self.assertEqual(block_dict, {
            'type': 'sequential',
            'name': 'sequential_block',
            'children': [
                {'type': 'stage', 'name': 'stage1'},
                {'type': 'stage', 'name': 'stage2'}
            ]
        })

    def test_sequential_block_config_empty_children(self):
        """Test SequentialBlockConfig with empty children list."""
        block = SequentialBlockConfig("empty_block", [])

        self.assertEqual(block.name, "empty_block")
        self.assertEqual(len(block.children), 0)

        # Test to_dict conversion
        block_dict = block.to_dict()
        self.assertEqual(block_dict, {
            'type': 'sequential',
            'name': 'empty_block',
            'children': []
        })

    def test_parallel_block_config(self):
        """Test ParallelBlockConfig dataclass."""
        stage1 = StageConfig("branch1")
        stage2 = StageConfig("branch2")

        block = ParallelBlockConfig("parallel_block", [stage1, stage2])

        self.assertEqual(block.name, "parallel_block")
        self.assertEqual(len(block.children), 2)
        self.assertEqual(block.children[0].name, "branch1")
        self.assertEqual(block.children[1].name, "branch2")

        # Test to_dict conversion
        block_dict = block.to_dict()
        self.assertEqual(block_dict, {
            'type': 'parallel',
            'name': 'parallel_block',
            'children': [
                {'type': 'stage', 'name': 'branch1'},
                {'type': 'stage', 'name': 'branch2'}
            ]
        })

    def test_parallel_block_config_empty_children(self):
        """Test ParallelBlockConfig with empty children list."""
        block = ParallelBlockConfig("empty_parallel", [])

        self.assertEqual(block.name, "empty_parallel")
        self.assertEqual(len(block.children), 0)

        # Test to_dict conversion
        block_dict = block.to_dict()
        self.assertEqual(block_dict, {
            'type': 'parallel',
            'name': 'empty_parallel',
            'children': []
        })

    def test_dag_config(self):
        """Test DAGConfig dataclass."""
        root = SequentialBlockConfig(
            "root",
            [StageConfig("stage1"), StageConfig("stage2")]
        )

        params = {"stage1": {"param": "value"}}
        dag = DAGConfig(root=root, params=params)

        self.assertEqual(dag.root, root)
        self.assertEqual(dag.params, params)

        # Test to_dict conversion
        dag_dict = dag.to_dict()
        self.assertEqual(dag_dict, {
            'type': 'sequential',
            'name': 'root',
            'children': [
                {'type': 'stage', 'name': 'stage1'},
                {'type': 'stage', 'name': 'stage2'}
            ]
        })

        # Test get_all_stage_names
        stage_names = dag.get_all_stage_names()
        self.assertEqual(stage_names, ["stage1", "stage2"])

    def test_dag_config_empty_params(self):
        """Test DAGConfig with empty params."""
        root = SequentialBlockConfig("root", [StageConfig("stage1")])
        dag = DAGConfig(root=root, params={})

        self.assertEqual(dag.params, {})

        # Test get_all_stage_names still works
        stage_names = dag.get_all_stage_names()
        self.assertEqual(stage_names, ["stage1"])

    def test_dag_config_conflicting_params(self):
        """Test DAGConfig with conflicting params (DAG vs pipeline config)."""
        root = SequentialBlockConfig("root", [StageConfig("stage1")])
        dag = DAGConfig(root=root, params={"stage1": {"dag_param": "dag_value"}})

        pipeline_config = {
            'params': {'stage1': {'pipeline_param': 'pipeline_value'}},
            'export_flags': {},
            'name': 'test',
            'version': '1.0'
        }

        # DAG params should override pipeline params for the same stage
        with patch('plinth.dag_structures.build_dag_from_dict') as mock_build:
            dag.build_block_tree(pipeline_config)

            call_args = mock_build.call_args
            config_dict = call_args[0][1]

            # DAG params should take precedence
            self.assertEqual(config_dict['params']['stage1'], {"dag_param": "dag_value"})

    @patch('plinth.dag_structures.build_dag_from_dict')
    def test_dag_config_build_block_tree(self, mock_build):
        """Test DAGConfig.build_block_tree method."""
        mock_block = Mock()
        mock_build.return_value = mock_block

        root = SequentialBlockConfig("root", [StageConfig("stage1")])
        dag = DAGConfig(root=root, params={"stage1": {"param": "value"}})

        pipeline_config = {
            'params': {'existing': 'param'},
            'export_flags': {'flag': True},
            'name': 'test_pipeline',
            'version': '1.0'
        }

        result = dag.build_block_tree(pipeline_config)

        self.assertEqual(result, mock_block)
        mock_build.assert_called_once()

        # Verify the config dict passed to build_dag_from_dict
        call_args = mock_build.call_args
        config_dict = call_args[0][1]

        self.assertEqual(config_dict['params'], {
            'existing': 'param',
            'stage1': {'param': 'value'}
        })
        self.assertEqual(config_dict['export_flags'], {'flag': True})
        self.assertEqual(config_dict['name'], 'test_pipeline')
        self.assertEqual(config_dict['version'], '1.0')


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions for creating common DAG patterns."""

    def test_create_simple_sequential_pipeline(self):
        """Test create_simple_sequential_pipeline function."""
        stages = ["stage1", "stage2", "stage3"]
        params = {"stage1": {"param": "value"}}

        dag = create_simple_sequential_pipeline("test_pipeline", stages, params)

        self.assertIsInstance(dag.root, SequentialBlockConfig)
        self.assertEqual(dag.root.name, "test_pipeline")
        self.assertEqual(len(dag.root.children), 3)
        self.assertEqual(dag.params, params)

        stage_names = dag.get_all_stage_names()
        self.assertEqual(stage_names, ["stage1", "stage2", "stage3"])

    def test_create_fan_out_pipeline(self):
        """Test create_fan_out_pipeline function."""
        prepare = ["load", "clean"]
        branches = ["branch_a", "branch_b"]
        after = ["merge", "report"]
        params = {"branch_a": {"size": 4}}

        dag = create_fan_out_pipeline(
            prepare, branches, after, params
        )

        self.assertIsInstance(dag.root, SequentialBlockConfig)
        self.assertEqual(len(dag.root.children), 3)

        # Check prepare block
        before_block = dag.root.children[0]
        self.assertEqual(before_block.name, "before")
        self.assertEqual(len(before_block.children), 2)

        # Check fan-out block
        fan_out_block = dag.root.children[1]
        self.assertEqual(fan_out_block.name, "fan_out")
        self.assertEqual(len(fan_out_block.children), 2)

        # Check after block
        after_block = dag.root.children[2]
        self.assertEqual(after_block.name, "after")
        self.assertEqual(len(after_block.children), 2)

        self.assertEqual(dag.params, params)

    def test_create_nested_parallel_pipeline(self):
        """Test create_nested_parallel_pipeline function."""
        prepare = SequentialBlockConfig(
            "prepare",
            [StageConfig("load"), StageConfig("clean")]
        )

        branches = ParallelBlockConfig(
            "branches",
            [StageConfig("branch_a"), StageConfig("branch_b")]
        )

        dag = create_nested_parallel_pipeline([prepare, branches])

        self.assertIsInstance(dag.root, SequentialBlockConfig)
        self.assertEqual(len(dag.root.children), 2)
        self.assertEqual(dag.root.children[0], prepare)
        self.assertEqual(dag.root.children[1], branches)

        stage_names = dag.get_all_stage_names()
        self.assertEqual(stage_names, ["load", "clean", "branch_a", "branch_b"])

    def test_convenience_functions_custom_parameters(self):
        """Test convenience functions with custom parameters."""
        # Test create_simple_sequential_pipeline with custom params
        dag1 = create_simple_sequential_pipeline(
            "test_pipeline",
            ["stage1", "stage2"],
            {"stage1": {"param1": "value1"}, "stage2": {"param2": "value2"}}
        )

        self.assertEqual(dag1.params["stage1"]["param1"], "value1")
        self.assertEqual(dag1.params["stage2"]["param2"], "value2")

        # Test create_fan_out_pipeline with custom params
        dag2 = create_fan_out_pipeline(
            ["pre1"], ["branch1", "branch2"], ["post1"],
            {"branch1": {"custom": "param"}}
        )

        self.assertEqual(dag2.params["branch1"]["custom"], "param")

    def test_convenience_functions_empty_stage_lists(self):
        """Test convenience functions with empty stage lists."""
        # Test with empty before stages
        dag1 = create_fan_out_pipeline(
            [], ["branch1", "branch2"], ["post1"]
        )

        self.assertEqual(len(dag1.root.children), 2)  # Only fan_out and after
        self.assertEqual(dag1.root.children[0].name, "fan_out")
        self.assertEqual(dag1.root.children[1].name, "after")

        # Test with empty parallel stages
        dag2 = create_fan_out_pipeline(
            ["pre1"], [], ["post1"]
        )

        self.assertEqual(len(dag2.root.children), 2)  # Only before and after
        self.assertEqual(dag2.root.children[0].name, "before")
        self.assertEqual(dag2.root.children[1].name, "after")

        # Test with empty after stages
        dag3 = create_fan_out_pipeline(
            ["pre1"], ["branch1", "branch2"], []
        )

        self.assertEqual(len(dag3.root.children), 2)  # Only before and fan_out
        self.assertEqual(dag3.root.children[0].name, "before")
        self.assertEqual(dag3.root.children[1].name, "fan_out")


class TestNestedStructures(unittest.TestCase):
    """Test nested block structures."""

    def test_nested_sequential_in_parallel(self):
        """Test sequential blocks nested within parallel blocks."""
        # Create nested structure: parallel -> sequential -> stages
        inner_seq1 = SequentialBlockConfig(
            "branch1_processing",
            [StageConfig("stage1a"), StageConfig("stage1b")]
        )

        inner_seq2 = SequentialBlockConfig(
            "branch2_processing",
            [StageConfig("stage2a"), StageConfig("stage2b")]
        )

        parallel_block = ParallelBlockConfig(
            "parallel_processing",
            [inner_seq1, inner_seq2]
        )

        root = SequentialBlockConfig("root", [parallel_block])
        dag = DAGConfig(root=root)

        stage_names = dag.get_all_stage_names()
        self.assertEqual(stage_names, ["stage1a", "stage1b", "stage2a", "stage2b"])

        # Test to_dict conversion
        dag_dict = dag.to_dict()
        self.assertEqual(dag_dict['type'], 'sequential')
        self.assertEqual(dag_dict['name'], 'root')
        self.assertEqual(len(dag_dict['children']), 1)

        parallel_dict = dag_dict['children'][0]
        self.assertEqual(parallel_dict['type'], 'parallel')
        self.assertEqual(parallel_dict['name'], 'parallel_processing')
        self.assertEqual(len(parallel_dict['children']), 2)

        # Check nested sequential blocks
        for child in parallel_dict['children']:
            self.assertEqual(child['type'], 'sequential')
            self.assertEqual(len(child['children']), 2)
