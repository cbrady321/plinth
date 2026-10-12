
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from plinth.base_stage import BaseStage
from plinth.blocks import ParallelBlock, StageNode
from plinth.context import FileSystemStageContext
from plinth.dataset.structures import DatasetManifest, DatasetSchema
from plinth.intent import StageIntent
from plinth.results import StageOutcome


# Mock stage for testing
class MockStage(BaseStage):
    def __init__(self, stage_name: str, config: Dict[str, Any], intent: StageIntent = None):
        super().__init__(stage_name, config)
        self._intent = intent or StageIntent()

    def get_intent(self) -> StageIntent:
        return self._intent

    def process_file(self, input_path: Path, output_path: Path, metadata: Dict[str, Any]) -> StageOutcome:
        if self._intent.modifies_files:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write("processed")
            return StageOutcome.update(processed=True, path=str(output_path))
        return StageOutcome.update(processed=True)

class TestDatasetManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = DatasetManifest()

    def test_add_row(self):
        row = {
            'entity_id': 'p1',
            'batch': 1,
            'slot': None,
            'filename': 'file1.bin',
            'file_path': '/tmp/file1.bin'
        }
        self.manifest.add_row(row)
        self.assertEqual(len(self.manifest), 1)
        self.assertEqual(self.manifest[0]['entity_id'], 'p1')

    def test_merge_no_conflict(self):
        m1 = DatasetManifest()
        m1.add_row({'entity_id': 'p1', 'batch': 1, 'slot': None, 'col1': 'val1'})

        m2 = DatasetManifest()
        m2.add_row({'entity_id': 'p1', 'batch': 1, 'slot': None, 'col2': 'val2'})

        merged = m1.merge(m2)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['col1'], 'val1')
        self.assertEqual(merged[0]['col2'], 'val2')

    def test_merge_conflict(self):
        m1 = DatasetManifest()
        m1.add_row({'entity_id': 'p1', 'batch': 1, 'slot': None, 'col1': 'val1'})

        m2 = DatasetManifest()
        m2.add_row({'entity_id': 'p1', 'batch': 1, 'slot': None, 'col1': 'val2'}) # Conflict
        merged = m1.merge(m2)
        self.assertEqual(merged[0]['col1'], 'val2')

    def test_merge_deduplication(self):
        m1 = DatasetManifest()
        m1.add_row({'entity_id': 'p1', 'batch': 1, 'slot': None, 'col1': 'val1'})

        m2 = DatasetManifest()
        m2.add_row({'entity_id': 'p1', 'batch': 1, 'slot': None, 'col1': 'val1'}) # Same value

        merged = m1.merge(m2)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['col1'], 'val1')

class TestDatasetSchema(unittest.TestCase):
    def test_validation(self):
        schema = DatasetSchema(columns={'required_col': 'str'})
        df = pd.DataFrame([{'other_col': 1}]) # Missing required_col

        with self.assertRaisesRegex(ValueError, "missing required columns"):
            schema.validate_dataframe(df)

    def test_unique_key_validation(self):
        schema = DatasetSchema(unique_key=['id'])
        df = pd.DataFrame([{'id': 1}, {'id': 1}]) # Duplicate id

        with self.assertRaisesRegex(ValueError, "Duplicate entries found"):
            schema.validate_dataframe(df)

class TestBaseStage(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.input_dir = self.test_dir / "input"
        self.output_dir = self.test_dir / "output"
        self.input_dir.mkdir()

        # Create input manifest
        self.manifest = DatasetManifest()
        self.manifest.add_row({
            'entity_id': 'p1',
            'batch': 1,
            'slot': None,
            'filename': 'test.bin',
            'file_path': str(self.input_dir / 'test.bin')
        })
        self.manifest.to_csv(self.input_dir / "manifest.csv")

        # Create dummy input file
        with open(self.input_dir / "test.bin", 'w') as f:
            f.write("dummy bytes")

        self.context = FileSystemStageContext(self.input_dir, self.output_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_execute_validation_failure(self):
        # Intent requires missing column
        intent = StageIntent(required_input_columns={'missing_col'})
        stage = MockStage("test_stage", {}, intent)

        with self.assertRaisesRegex(ValueError, "missing from manifest"):
            stage.execute(self.context)

    def test_execute_success_with_propagation(self):
        # Intent writes new column, propagates files by reference
        intent = StageIntent(
            write_columns={'new_col': 'bool'},
            modifies_files=False
        )
        stage = MockStage("test_stage", {}, intent)

        # Mock process_file to just update metadata
        from plinth.results import StageOutcome

        def mock_process(input_path, output_path, metadata):
            return StageOutcome.update(new_col=True)
        stage.process_file = mock_process

        stage.execute(self.context)

        # Check output
        out_manifest = DatasetManifest.from_csv(self.output_dir / "manifest.csv")
        self.assertEqual(out_manifest[0]['new_col'], True)
        self.assertEqual(out_manifest[0]['file_path'], str(self.input_dir / 'test.bin')) # Preserved absolute path

        # Check schema
        schema = DatasetSchema.from_yaml(self.output_dir / "dataset_schema.yaml")
        self.assertIn('new_col', schema.columns)

class TestParallelBlock(unittest.TestCase):
    def test_conflict_detection(self):
        # Child 1 writes 'col_A'
        child1 = StageNode("stage1", {'params': {'stage1': {}}})
        # Mock the _get_stage method to return a stage with specific intent
        child1._stage = MockStage("stage1", {}, StageIntent(write_columns={'col_A': 'str'}))

        # Child 2 writes 'col_A' (Conflict!)
        child2 = StageNode("stage2", {'params': {'stage2': {}}})
        child2._stage = MockStage("stage2", {}, StageIntent(write_columns={'col_A': 'int'}))

        block = ParallelBlock("parallel", {}, [child1, child2])

        # We need to mock constraints and paths since execute does FS operations
        # But conflict detection happens before execution loop in the updated code?
        # Actually, updated code checks conflicts at start of execute()

        # We can just call execute with dummy paths and expect ValueError
        with self.assertRaisesRegex(ValueError, "Parallel conflict"):
            block.execute([], Path("."), "a")

if __name__ == '__main__':
    unittest.main()

