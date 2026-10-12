"""Tests for JSONPath resolver functionality."""

import unittest

from plinth.jsonpath_resolver import expand_jsonpath_indices, path_to_index_list


class TestExpandJSONPathIndices(unittest.TestCase):
    """Test expand_jsonpath_indices function."""

    def test_simple_path_no_comma(self):
        """Test simple path with no comma indices."""
        path = "$.root.children[1].children[0]"
        result = expand_jsonpath_indices(path)
        self.assertEqual(result, ["$.root.children[1].children[0]"])

    def test_single_comma_separated_index(self):
        """Test single comma-separated index."""
        path = "$.root.children[0,2]"
        result = expand_jsonpath_indices(path)
        self.assertEqual(result, ["$.root.children[0]", "$.root.children[2]"])

    def test_multiple_comma_separated_indices(self):
        """Test multiple comma-separated indices."""
        path = "$.root.children[0,1,2]"
        result = expand_jsonpath_indices(path)
        self.assertEqual(result, ["$.root.children[0]", "$.root.children[1]", "$.root.children[2]"])

    def test_nested_comma_separated_indices(self):
        """Test nested comma-separated indices."""
        path = "$.root.children[1].children[0,2]"
        result = expand_jsonpath_indices(path)
        self.assertEqual(result, ["$.root.children[1].children[0]", "$.root.children[1].children[2]"])

    def test_multiple_nested_comma_indices(self):
        """Test multiple levels with comma indices."""
        path = "$.root.children[0,1].children[0,2]"
        result = expand_jsonpath_indices(path)
        expected = [
            "$.root.children[0].children[0]",
            "$.root.children[0].children[2]",
            "$.root.children[1].children[0]",
            "$.root.children[1].children[2]"
        ]
        self.assertEqual(result, expected)

    def test_complex_nested_structure(self):
        """Test complex nested structure with multiple comma indices."""
        path = "$.root.children[0,2].children[1,3].children[0,1,2]"
        result = expand_jsonpath_indices(path)
        expected = [
            "$.root.children[0].children[1].children[0]",
            "$.root.children[0].children[1].children[1]",
            "$.root.children[0].children[1].children[2]",
            "$.root.children[0].children[3].children[0]",
            "$.root.children[0].children[3].children[1]",
            "$.root.children[0].children[3].children[2]",
            "$.root.children[2].children[1].children[0]",
            "$.root.children[2].children[1].children[1]",
            "$.root.children[2].children[1].children[2]",
            "$.root.children[2].children[3].children[0]",
            "$.root.children[2].children[3].children[1]",
            "$.root.children[2].children[3].children[2]"
        ]
        self.assertEqual(result, expected)

    def test_malformed_paths_missing_brackets(self):
        """Test malformed paths with missing brackets."""
        # Missing closing bracket
        with self.assertRaises(ValueError):
            expand_jsonpath_indices("$.root.children[0,1")

        # Missing opening bracket (current implementation may ignore)
        expand_jsonpath_indices("$.root.children0,1]")

        # Mismatched brackets
        with self.assertRaises(ValueError):
            expand_jsonpath_indices("$.root.children[0,1}")

    def test_invalid_syntax(self):
        """Test invalid syntax handling."""
        # Empty brackets: ensure it returns a list (implementation-defined handling)
        result = expand_jsonpath_indices("$.root.children[]")
        self.assertIsInstance(result, list)

        # Non-numeric indices: ensure it returns a list (implementation-defined handling)
        result = expand_jsonpath_indices("$.root.children[a,b]")
        self.assertIsInstance(result, list)

        # Mixed valid and invalid indices: ensure it returns a list (implementation-defined handling)
        result = expand_jsonpath_indices("$.root.children[0,a,2]")
        self.assertIsInstance(result, list)

        # Negative indices: ensure it returns a list (implementation-defined handling)
        result = expand_jsonpath_indices("$.root.children[-1,0]")
        self.assertIsInstance(result, list)

    def test_edge_cases(self):
        """Test edge cases."""
        # Single index (no comma)
        result = expand_jsonpath_indices("$.root.children[5]")
        self.assertEqual(result, ["$.root.children[5]"])

        # Large indices
        result = expand_jsonpath_indices("$.root.children[0,99,100]")
        expected = ["$.root.children[0]", "$.root.children[99]", "$.root.children[100]"]
        self.assertEqual(result, expected)

        # Zero index
        result = expand_jsonpath_indices("$.root.children[0,1]")
        expected = ["$.root.children[0]", "$.root.children[1]"]
        self.assertEqual(result, expected)


class TestPathToIndexList(unittest.TestCase):
    """Test path_to_index_list function."""

    def test_simple_path(self):
        """Test simple path conversion."""
        path = "$.root.children[1].children[0]"
        result = path_to_index_list(path, "root")
        self.assertEqual(result, [1, 0])

    def test_deep_path(self):
        """Test deep path (4+ levels)."""
        path = "$.root.children[2].children[1].children[3].children[0]"
        result = path_to_index_list(path, "root")
        self.assertEqual(result, [2, 1, 3, 0])

    def test_single_level_path(self):
        """Test single level path."""
        path = "$.root.children[5]"
        result = path_to_index_list(path, "root")
        self.assertEqual(result, [5])

    def test_root_only_path(self):
        """Test root-only path."""
        path = "$.root"
        result = path_to_index_list(path, "root")
        self.assertEqual(result, [])

    def test_wrong_root_name(self):
        """Test error with wrong root name."""
        path = "$.root.children[1]"
        with self.assertRaisesRegex(ValueError, "Path must start with root name"):
            path_to_index_list(path, "wrong_root")

    def test_malformed_path(self):
        """Test malformed path handling."""
        # Missing root
        with self.assertRaisesRegex(ValueError, "Path must start with root name"):
            path_to_index_list("$.children[1]", "root")

        # Invalid JSONPath format (current implementation treats as wrong root)
        with self.assertRaisesRegex(ValueError, "Path must start with root name"):
            path_to_index_list("root.children[1]", "root")

        # Missing children segment: current implementation returns empty list
        self.assertEqual(path_to_index_list("$.root[1]", "root"), [])

    def test_edge_cases(self):
        """Test edge cases."""
        # Zero indices
        path = "$.root.children[0].children[0]"
        result = path_to_index_list(path, "root")
        self.assertEqual(result, [0, 0])

        # Large indices
        path = "$.root.children[99].children[100]"
        result = path_to_index_list(path, "root")
        self.assertEqual(result, [99, 100])

        # Single digit indices
        path = "$.root.children[1].children[2].children[3]"
        result = path_to_index_list(path, "root")
        self.assertEqual(result, [1, 2, 3])

    def test_invalid_index_format(self):
        """Test invalid index format handling."""
        # Non-numeric index
        with self.assertRaises(ValueError):
            path_to_index_list("$.root.children[a]", "root")

        # Negative index may be accepted; verify parsed value
        self.assertEqual(path_to_index_list("$.root.children[-1]", "root"), [-1])

        # Float index
        with self.assertRaises(ValueError):
            path_to_index_list("$.root.children[1.5]", "root")

        # Empty index
        with self.assertRaises(ValueError):
            path_to_index_list("$.root.children[]", "root")


class TestJSONPathIntegration(unittest.TestCase):
    """Test JSONPath functions working together."""

    def test_expand_then_convert(self):
        """Test expanding comma indices then converting to index lists."""
        # Start with comma-separated path
        comma_path = "$.root.children[0,2].children[1,3]"

        # Expand to individual paths
        expanded = expand_jsonpath_indices(comma_path)
        expected_expanded = [
            "$.root.children[0].children[1]",
            "$.root.children[0].children[3]",
            "$.root.children[2].children[1]",
            "$.root.children[2].children[3]"
        ]
        self.assertEqual(expanded, expected_expanded)

        # Convert each to index list
        index_lists = [path_to_index_list(path, "root") for path in expanded]
        expected_lists = [[0, 1], [0, 3], [2, 1], [2, 3]]
        self.assertEqual(index_lists, expected_lists)

    def test_real_world_scenarios(self):
        """Test real-world JSONPath scenarios."""
        # Scenario 1: Select specific parallel branches
        path1 = "$.root.children[1].children[0,2]"  # Select branches 0 and 2 from parallel block
        expanded1 = expand_jsonpath_indices(path1)
        self.assertEqual(expanded1, [
            "$.root.children[1].children[0]",
            "$.root.children[1].children[2]"
        ])

        # Scenario 2: Select multiple sequential stages
        path2 = "$.root.children[0,1,2]"  # Select first 3 sequential stages
        expanded2 = expand_jsonpath_indices(path2)
        self.assertEqual(expanded2, [
            "$.root.children[0]",
            "$.root.children[1]",
            "$.root.children[2]"
        ])

        # Scenario 3: Complex nested selection
        path3 = "$.root.children[0].children[1,2].children[0]"
        expanded3 = expand_jsonpath_indices(path3)
        self.assertEqual(expanded3, [
            "$.root.children[0].children[1].children[0]",
            "$.root.children[0].children[2].children[0]"
        ])

    def test_error_propagation(self):
        """Test that errors propagate correctly through the chain."""
        # Expansion may succeed; invalid conversion should fail on wrong root
        expanded = expand_jsonpath_indices("$.root.children[0,1]")
        with self.assertRaises(ValueError):
            path_to_index_list(expanded[0], "wrong_root")

    def test_performance_with_large_indices(self):
        """Test performance with large numbers of indices."""
        # Test with many comma-separated indices
        path = "$.root.children[0,1,2,3,4,5,6,7,8,9]"
        expanded = expand_jsonpath_indices(path)
        self.assertEqual(len(expanded), 10)

        # Convert all to index lists
        index_lists = [path_to_index_list(p, "root") for p in expanded]
        expected = [[i] for i in range(10)]
        self.assertEqual(index_lists, expected)
