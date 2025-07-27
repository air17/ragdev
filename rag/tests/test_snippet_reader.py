from unittest.mock import patch
from pathlib import Path

from rag.snippet_reader import read_snippets, _read_single_snippet, SearchResult


class TestSnippetReader:
    @patch("pathlib.Path.open")
    def test_read_single_snippet(self, mock_file):
        # Setup mock file with lines
        file_content = "line1\nline2\nline3\nline4\nline5\n"
        mock_file.return_value.__enter__.return_value.readlines.return_value = (
            file_content.split("\n")
        )

        # Call the function for lines 2-4
        result = _read_single_snippet(Path("test.py"), 2, 4)

        # Verify result
        assert result == "line2line3line4"

    @patch("pathlib.Path.open")
    def test_read_single_snippet_invalid_range(self, mock_file):
        # Setup mock file
        file_content = "line1\nline2\nline3\n"
        mock_file.return_value.__enter__.return_value.readlines.return_value = (
            file_content.split("\n")
        )

        # Test invalid range (start > end)
        result = _read_single_snippet(Path("test.py"), 5, 3)
        assert result == ""

        # Test out of bounds range
        result = _read_single_snippet(Path("test.py"), 4, 10)
        assert result == ""

    @patch("pathlib.Path.open", side_effect=FileNotFoundError)
    def test_read_single_snippet_file_not_found(self, mock_file):
        # Test with non-existent file
        result = _read_single_snippet(Path("nonexistent.py"), 1, 5)
        assert result == ""

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
        with patch("rag.snippet_reader._read_single_snippet") as mock_read:
            # Configure mock to return different snippets based on input
            def side_effect(path, start, end):
                if path.name == "test1.py":
                    return "snippet1"
                elif path.name == "test2.py":
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
        with patch("rag.snippet_reader._read_single_snippet") as mock_read:
            mock_read.return_value = "code snippet"

            # Call the function with base_dir
            results = read_snippets(search_results, base_dir="/base/dir")

            # Verify mock was called with correct combined path
            expected_path = Path("/base/dir/relative/path.py")
            mock_read.assert_called_once_with(expected_path, 1, 5)

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
        with patch("rag.snippet_reader._read_single_snippet", return_value=""):
            # Call the function
            results = read_snippets(search_results)

            # Verify empty results (entry should be skipped)
            assert len(results) == 0
