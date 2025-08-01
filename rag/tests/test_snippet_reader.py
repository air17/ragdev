from unittest.mock import patch

from rag.snippet_reader import read_snippets, SearchResult


class TestSnippetReader:
    def test_read_snippets(self):
        # Create test search results
        search_results = [
            SearchResult(
                id=1,
                distance=0.8,
                entity={"filename": "test1.py", "start_line": 10, "end_line": 15},
            ),
            SearchResult(
                id=2,
                distance=0.7,
                entity={"filename": "test2.py", "start_line": 5, "end_line": 8},
            ),
            # Result without entity should be skipped
            {"id": 3, "distance": 0.6},
            # Result without filename should be skipped
            {"id": 4, "distance": 0.5, "entity": {"start_line": 1, "end_line": 5}},
        ]

        # Mock _read_single_snippet
        with patch("rag.snippet_reader.read_file") as mock_read:
            # Configure mock to return different snippets based on input
            def side_effect(path, start, end, add_line_numbers):
                if path == "test1.py":
                    return "snippet1"
                elif path == "test2.py":
                    return "snippet2"
                return ""

            mock_read.side_effect = side_effect

            # Call the function
            results = read_snippets(search_results)

            # Verify results
            assert len(results) == 2
            assert results[0]["id"] == 1
            assert results[0]["snippet"] == "snippet1"
            assert results[1]["id"] == 2
            assert results[1]["snippet"] == "snippet2"

    def test_read_snippets_with_base_dir(self):
        # Create test search result with relative path
        search_results = [
            SearchResult(
                id=1,
                distance=0.8,
                entity={"filename": "relative/path.py", "start_line": 1, "end_line": 5},
            ),
        ]

        # Mock _read_single_snippet
        with patch("rag.snippet_reader.read_file") as mock_read:
            mock_read.return_value = "code snippet"

            # Call the function with base_dir
            results = read_snippets(search_results, base_dir="/base/dir")

            # Verify mock was called with correct combined path
            expected_path = "/base/dir/relative/path.py"
            mock_read.assert_called_once_with(
                expected_path, 1, 5, add_line_numbers=True
            )

            # Verify result
            assert len(results) == 1
            assert results[0]["snippet"] == "code snippet"

    def test_read_snippets_empty_snippet(self):
        # Create test search results
        search_results = [
            SearchResult(
                id=1,
                distance=0.8,
                entity={"filename": "test.py", "start_line": 1, "end_line": 5},
            ),
        ]

        # Mock _read_single_snippet to return empty string
        with patch("rag.snippet_reader.read_file", return_value=""):
            # Call the function
            results = read_snippets(search_results)

            # Verify empty results (entry should be skipped)
            assert len(results) == 0
