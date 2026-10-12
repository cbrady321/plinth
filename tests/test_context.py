"""Tests for stage context functionality."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from plinth.context import FileSystemStageContext, MultiInputStageContext
from plinth.dataset.structures import DatasetManifest, MetadataLedger, MetadataLedgerEntry


class TestFileSystemStageContext(unittest.TestCase):
    """Test FileSystemStageContext."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.input_dir = self.temp_dir / "input"
        self.output_dir = self.temp_dir / "output"
        self.input_dir.mkdir()

        # Create test files
        (self.input_dir / "test.bin").write_text("file data")
        (self.input_dir / "metadata.yaml").write_text("metadata: test")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_basic_properties(self):
        """Test basic context properties."""
        context = FileSystemStageContext(self.input_dir, self.output_dir)

        self.assertEqual(context.get_input_dir(), self.input_dir)
        self.assertEqual(context.get_output_dir(), self.output_dir)
        self.assertIsNone(context.get_manifest())

    def test_with_manifest(self):
        """Test context with manifest."""
        manifest = DatasetManifest()
        context = FileSystemStageContext(self.input_dir, self.output_dir, manifest)

        self.assertEqual(context.get_manifest(), manifest)

    def test_ledger_loading(self):
        """Test ledger loading from input directory."""
        # Create a test ledger
        ledger = MetadataLedger()
        entry = MetadataLedgerEntry(
            stage_name="test_stage",
            timestamp="2023-01-01T00:00:00",
            function_name="TestStage",
            input_directory=str(self.input_dir),
            output_directory=str(self.output_dir),
            input_hash="test_hash",
            output_hash="test_hash",
            params_hash="test_hash",
            params={},
            files_processed=1,
            duration_seconds=1.0
        )
        ledger.append(entry)
        ledger.to_yaml(self.input_dir / "metadata_ledger.yaml")

        # Test context loads the ledger
        context = FileSystemStageContext(self.input_dir, self.output_dir)
        loaded_ledger = context.get_ledger()

        self.assertEqual(len(loaded_ledger.entries), 1)
        self.assertEqual(loaded_ledger.entries[0].stage_name, "test_stage")

    def test_ledger_creation_when_missing(self):
        """Test ledger creation when no ledger exists."""
        context = FileSystemStageContext(self.input_dir, self.output_dir)
        ledger = context.get_ledger()

        # Should create empty ledger
        self.assertIsInstance(ledger, MetadataLedger)
        self.assertEqual(len(ledger.entries), 0)

    def test_manifest_loading(self):
        """Test manifest loading from input directory."""
        # Create a test manifest
        manifest = DatasetManifest()
        manifest.to_csv(self.input_dir / "manifest.csv")

        # Test context loads the manifest
        context = FileSystemStageContext(self.input_dir, self.output_dir)
        loaded_manifest = context.get_manifest()

        self.assertIsNotNone(loaded_manifest)
        self.assertIsInstance(loaded_manifest, DatasetManifest)

    def test_manifest_creation_when_missing(self):
        """Test manifest creation when no manifest exists."""
        context = FileSystemStageContext(self.input_dir, self.output_dir)
        manifest = context.get_manifest()

        # Should return None when no manifest exists
        self.assertIs(manifest, None)

    def test_update_manifest(self):
        """Test manifest update functionality."""
        manifest = DatasetManifest()
        context = FileSystemStageContext(self.input_dir, self.output_dir, manifest)

        # Create updates as a dataframe-backed manifest
        updates = DatasetManifest(
            pd.DataFrame(
                [
                    {
                        "entity_id": "e1",
                        "batch": 1,
                        "slot": None,
                        "filename": "test1.bin",
                        "file_path": "/path/to/test1.bin",
                    },
                    {
                        "entity_id": "e2",
                        "batch": 1,
                        "slot": None,
                        "filename": "test2.bin",
                        "file_path": "/path/to/test2.bin",
                    },
                ]
            )
        )

        # Update manifest
        context.update_manifest(updates)

        # Check that manifest was written to output directory
        manifest_path = self.output_dir / "manifest.csv"
        self.assertTrue(manifest_path.exists())


class TestMultiInputStageContext(unittest.TestCase):
    """Test MultiInputStageContext functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.input1 = self.temp_dir / "input1"
        self.input2 = self.temp_dir / "input2"
        self.input3 = self.temp_dir / "input3"
        self.output_dir = self.temp_dir / "output"

        # Create input directories
        self.input1.mkdir()
        self.input2.mkdir()
        self.input3.mkdir()

        # Create test files
        (self.input1 / "file1.bin").write_text("file 1")
        (self.input2 / "file2.bin").write_text("file 2")
        (self.input3 / "file3.bin").write_text("file 3")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_basic_properties(self):
        """Test basic multi-input context properties."""
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)

        self.assertEqual(context.get_input_dir(), self.input1)  # First input as primary
        self.assertEqual(context.get_input_dirs(), [self.input1, self.input2])
        self.assertEqual(context.get_output_dir(), self.output_dir)
        self.assertIsNone(context.get_manifest())

    def test_with_manifest(self):
        """Test multi-input context with manifest."""
        manifest = DatasetManifest()
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir, manifest)

        self.assertEqual(context.get_manifest(), manifest)

    def test_ledger_merging_from_multiple_inputs(self):
        """Test ledger merging from multiple input directories."""
        # Create ledgers in input directories
        ledger1 = MetadataLedger()
        entry1 = MetadataLedgerEntry(
            stage_name="stage1",
            timestamp="2023-01-01T00:00:00",
            function_name="Stage1",
            input_directory=str(self.input1),
            output_directory=str(self.input1),
            input_hash="hash1",
            output_hash="hash1",
            params_hash="hash1",
            params={"param1": "value1"},
            files_processed=1,
            duration_seconds=1.0
        )
        ledger1.append(entry1)
        ledger1.to_yaml(self.input1 / "metadata_ledger.yaml")

        ledger2 = MetadataLedger()
        entry2 = MetadataLedgerEntry(
            stage_name="stage2",
            timestamp="2023-01-01T01:00:00",
            function_name="Stage2",
            input_directory=str(self.input2),
            output_directory=str(self.input2),
            input_hash="hash2",
            output_hash="hash2",
            params_hash="hash2",
            params={"param2": "value2"},
            files_processed=2,
            duration_seconds=2.0
        )
        ledger2.append(entry2)
        ledger2.to_yaml(self.input2 / "metadata_ledger.yaml")

        # Test context merges ledgers
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_ledger = context.get_ledger()

        self.assertEqual(len(merged_ledger.entries), 2)
        self.assertEqual(merged_ledger.entries[0].stage_name, "stage1")
        self.assertEqual(merged_ledger.entries[1].stage_name, "stage2")
        self.assertEqual(merged_ledger.entries[0].params, {"param1": "value1"})
        self.assertEqual(merged_ledger.entries[1].params, {"param2": "value2"})

    def test_ledger_merging_with_missing_ledgers(self):
        """Test ledger merging when some inputs have no ledgers."""
        # Create ledger only in first input
        ledger1 = MetadataLedger()
        entry1 = MetadataLedgerEntry(
            stage_name="stage1",
            timestamp="2023-01-01T00:00:00",
            function_name="Stage1",
            input_directory=str(self.input1),
            output_directory=str(self.input1),
            input_hash="hash1",
            output_hash="hash1",
            params_hash="hash1",
            params={},
            files_processed=1,
            duration_seconds=1.0
        )
        ledger1.append(entry1)
        ledger1.to_yaml(self.input1 / "metadata_ledger.yaml")

        # No ledger in input2

        # Test context handles missing ledgers gracefully
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_ledger = context.get_ledger()

        self.assertEqual(len(merged_ledger.entries), 1)
        self.assertEqual(merged_ledger.entries[0].stage_name, "stage1")

    def test_ledger_merging_with_no_ledgers(self):
        """Test ledger merging when no inputs have ledgers."""
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_ledger = context.get_ledger()

        # Should create empty ledger
        self.assertIsInstance(merged_ledger, MetadataLedger)
        self.assertEqual(len(merged_ledger.entries), 0)

    def test_manifest_merging_from_multiple_inputs(self):
        """Test manifest merging from multiple input directories."""
        # Create manifests in input directories
        manifest1 = DatasetManifest()
        manifest1.to_csv(self.input1 / "manifest.csv")

        manifest2 = DatasetManifest()
        manifest2.to_csv(self.input2 / "manifest.csv")

        # Test context merges manifests
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_manifest = context.get_manifest()

        self.assertIsNotNone(merged_manifest)
        self.assertIsInstance(merged_manifest, DatasetManifest)

    def test_manifest_merging_with_missing_manifests(self):
        """Test manifest merging when some inputs have no manifests."""
        # Create manifest only in first input
        manifest1 = DatasetManifest()
        manifest1.to_csv(self.input1 / "manifest.csv")

        # No manifest in input2

        # Test context handles missing manifests gracefully
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_manifest = context.get_manifest()

        self.assertIsNotNone(merged_manifest)
        self.assertIsInstance(merged_manifest, DatasetManifest)

    def test_manifest_merging_with_no_manifests(self):
        """Test manifest merging when no inputs have manifests."""
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_manifest = context.get_manifest()

        # Should return None when no manifests exist
        self.assertIs(merged_manifest, None)

    def test_update_manifest_merges_correctly(self):
        """Test update_manifest merges correctly."""
        # Create manifests in input directories
        manifest1 = DatasetManifest()
        manifest1.to_csv(self.input1 / "manifest.csv")

        manifest2 = DatasetManifest()
        manifest2.to_csv(self.input2 / "manifest.csv")

        # Create context with additional manifest
        additional_manifest = DatasetManifest()
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir, additional_manifest)

        # Create updates as a dataframe-backed manifest
        updates = DatasetManifest(
            pd.DataFrame(
                [
                    {
                        "entity_id": "e1",
                        "batch": 1,
                        "slot": None,
                        "filename": "test1.bin",
                        "file_path": "/path/to/test1.bin",
                    },
                    {
                        "entity_id": "e2",
                        "batch": 1,
                        "slot": None,
                        "filename": "test2.bin",
                        "file_path": "/path/to/test2.bin",
                    },
                ]
            )
        )

        # Update manifest
        context.update_manifest(updates)

        # Check that merged manifest was written to output directory
        manifest_path = self.output_dir / "manifest.csv"
        self.assertTrue(manifest_path.exists())

    def test_three_input_directories(self):
        """Test context with three input directories."""
        context = MultiInputStageContext([self.input1, self.input2, self.input3], self.output_dir)

        self.assertEqual(context.get_input_dir(), self.input1)  # First input as primary
        self.assertEqual(context.get_input_dirs(), [self.input1, self.input2, self.input3])

        # Test that files from all inputs are accessible
        input_dirs = context.get_input_dirs()
        all_files = []
        for input_dir in input_dirs:
            all_files.extend(list(input_dir.glob("*.bin")))

        self.assertEqual(len(all_files), 3)
        self.assertTrue(any("file1.bin" in str(f)) for f in all_files)
        self.assertTrue(any("file2.bin" in str(f)) for f in all_files)
        self.assertTrue(any("file3.bin" in str(f)) for f in all_files)

    def test_single_input_directory(self):
        """Test context with single input directory (should work like FileSystemStageContext)."""
        context = MultiInputStageContext([self.input1], self.output_dir)

        self.assertEqual(context.get_input_dir(), self.input1)
        self.assertEqual(context.get_input_dirs(), [self.input1])
        self.assertEqual(context.get_output_dir(), self.output_dir)

    def test_empty_input_directories(self):
        """Test context with empty input directories list."""
        # Current implementation allows empty list, uses output_dir as primary
        context = MultiInputStageContext([], self.output_dir)
        self.assertEqual(context.get_input_dir(), self.output_dir)
        self.assertEqual(context.get_input_dirs(), [])

    def test_ledger_ordering_preservation(self):
        """Test that ledger entries maintain chronological order after merging."""
        # Create ledgers with different timestamps
        ledger1 = MetadataLedger()
        entry1 = MetadataLedgerEntry(
            stage_name="stage1",
            timestamp="2023-01-01T00:00:00",  # Earlier
            function_name="Stage1",
            input_directory=str(self.input1),
            output_directory=str(self.input1),
            input_hash="hash1",
            output_hash="hash1",
            params_hash="hash1",
            params={},
            files_processed=1,
            duration_seconds=1.0
        )
        ledger1.append(entry1)
        ledger1.to_yaml(self.input1 / "metadata_ledger.yaml")

        ledger2 = MetadataLedger()
        entry2 = MetadataLedgerEntry(
            stage_name="stage2",
            timestamp="2023-01-01T02:00:00",  # Later
            function_name="Stage2",
            input_directory=str(self.input2),
            output_directory=str(self.input2),
            input_hash="hash2",
            output_hash="hash2",
            params_hash="hash2",
            params={},
            files_processed=2,
            duration_seconds=2.0
        )
        ledger2.append(entry2)
        ledger2.to_yaml(self.input2 / "metadata_ledger.yaml")

        # Test that merged ledger maintains chronological order
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_ledger = context.get_ledger()

        self.assertEqual(len(merged_ledger.entries), 2)
        self.assertEqual(merged_ledger.entries[0].timestamp, "2023-01-01T00:00:00")
        self.assertEqual(merged_ledger.entries[1].timestamp, "2023-01-01T02:00:00")

    def test_ledger_duplicate_handling(self):
        """Test handling of duplicate ledger entries."""
        # Create identical ledgers in both inputs
        ledger = MetadataLedger()
        entry = MetadataLedgerEntry(
            stage_name="duplicate_stage",
            timestamp="2023-01-01T00:00:00",
            function_name="DuplicateStage",
            input_directory=str(self.input1),
            output_directory=str(self.input1),
            input_hash="hash",
            output_hash="hash",
            params_hash="hash",
            params={},
            files_processed=1,
            duration_seconds=1.0
        )
        ledger.append(entry)
        ledger.to_yaml(self.input1 / "metadata_ledger.yaml")
        ledger.to_yaml(self.input2 / "metadata_ledger.yaml")

        # Test that duplicates are preserved (not deduplicated)
        context = MultiInputStageContext([self.input1, self.input2], self.output_dir)
        merged_ledger = context.get_ledger()

        self.assertEqual(len(merged_ledger.entries), 2)
        self.assertEqual(merged_ledger.entries[0].stage_name, "duplicate_stage")
        self.assertEqual(merged_ledger.entries[1].stage_name, "duplicate_stage")


class TestContextTypeConsistency(unittest.TestCase):
    """Single- and multi-input contexts behave the same for one input."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.input_dir = self.temp_dir / "input"
        self.output_dir = self.temp_dir / "output"
        self.input_dir.mkdir()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_single_input_consistency(self):
        """Test that single-input MultiInputStageContext behaves like FileSystemStageContext."""
        # Create FileSystemStageContext
        fs_context = FileSystemStageContext(self.input_dir, self.output_dir)

        # Create MultiInputStageContext with single input
        mi_context = MultiInputStageContext([self.input_dir], self.output_dir)

        # Both should have same behavior
        self.assertEqual(fs_context.get_input_dir(), mi_context.get_input_dir())
        self.assertEqual(fs_context.get_output_dir(), mi_context.get_output_dir())
        self.assertEqual(fs_context.get_manifest(), mi_context.get_manifest())

    def test_interface_consistency(self):
        """Test that both context types implement the same interface."""
        fs_context = FileSystemStageContext(self.input_dir, self.output_dir)
        mi_context = MultiInputStageContext([self.input_dir], self.output_dir)

        # Both should have the same methods
        self.assertTrue(hasattr(fs_context, 'get_input_dir'))
        self.assertTrue(hasattr(fs_context, 'get_output_dir'))
        self.assertTrue(hasattr(fs_context, 'get_ledger'))
        self.assertTrue(hasattr(fs_context, 'get_manifest'))
        self.assertTrue(hasattr(fs_context, 'update_manifest'))

        self.assertTrue(hasattr(mi_context, 'get_input_dir'))
        self.assertTrue(hasattr(mi_context, 'get_output_dir'))
        self.assertTrue(hasattr(mi_context, 'get_ledger'))
        self.assertTrue(hasattr(mi_context, 'get_manifest'))
        self.assertTrue(hasattr(mi_context, 'update_manifest'))

        # MultiInputStageContext should have additional method
        self.assertTrue(hasattr(mi_context, 'get_input_dirs'))
        self.assertFalse(hasattr(fs_context, 'get_input_dirs'))
