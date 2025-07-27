import pytest
from unittest.mock import patch
import json

from find_usages.find_block import find_definitions, _load_index, _read_definition_code


@pytest.fixture
def mock_index_data():
    return [
        {
            "name": "TestClass",
            "fqn": "module.TestClass",
            "file": "test.py",
            "line": 10,
            "column": 6,
            "end_line": 20,
            "type": "class",
        },
        {
            "name": "test_func",
            "fqn": "module.test_func",
            "file": "test.py",
            "line": 25,
            "column": 4,
            "end_line": 30,
            "type": "function",
        },
        {
            "name": "TestClass",
            "fqn": "other.TestClass",
            "file": "other.py",
            "line": 5,
            "column": 6,
            "end_line": 15,
            "type": "class",
        },
        {
            "name": "TestClass",
            "fqn": "module.TestClass",
            "file": "imports.py",
            "line": 1,
            "column": 0,
            "end_line": 1,  # Same as line number indicates import
            "type": "class",
        },
    ]


class TestFindBlock:
    @patch("os.path.isfile")
    def test_load_index_file_not_found(self, mock_isfile):
        # Setup mock for index file not found
        mock_isfile.return_value = False

        # Call the function and verify it raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            _load_index("nonexistent.json")

    @patch("os.path.isfile")
    @patch("builtins.open")
    def test_load_index(self, mock_open, mock_isfile, mock_index_data):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )

        # Call the function
        result = _load_index("index.json")

        # Verify result
        assert result == mock_index_data

    @patch("builtins.open")
    def test_read_definition_code(self, mock_open):
        # Setup mock file with content
        file_content = "line1\nline2\nline3\nline4\nline5\n"
        mock_open.return_value.__enter__.return_value.readlines.return_value = (
            file_content.split("\n")
        )

        # Call the function to read lines 2-4
        result = _read_definition_code("test.py", 2, 5)

        # Verify result
        assert result == "line2line3line4line5"

    @patch("builtins.open")
    def test_read_definition_code_invalid_range(self, mock_open):
        # Setup mock file
        file_content = "line1\nline2\nline3\n"
        mock_open.return_value.__enter__.return_value.readlines.return_value = (
            file_content.split("\n")
        )

        # Test invalid range
        result = _read_definition_code("test.py", 5, 10)  # Beyond file length
        assert result is None

        result = _read_definition_code("test.py", -1, 2)  # Negative start
        assert result is None

    @patch("builtins.open", side_effect=Exception("File error"))
    def test_read_definition_code_exception(self, mock_open):
        # Test with file opening error
        result = _read_definition_code("test.py", 1, 5)
        assert result is None

    @patch("os.path.isfile")
    @patch("builtins.open")
    @patch("find_usages.find_block._read_definition_code")
    def test_find_definitions_by_name(
        self, mock_read_code, mock_open, mock_isfile, mock_index_data
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )
        mock_read_code.return_value = "class TestClass:\n    pass"

        # Call the function to find by simple name
        result = find_definitions("TestClass")

        # Verify results
        assert (
            len(result) == 2
        )  # Should find both TestClass definitions (excluding imports)

        # Check code was included
        assert "code" in result[0]
        assert result[0]["code"] == "class TestClass:\n    pass"

        # Verify imports were filtered out
        assert all(r["file"] != "imports.py" for r in result)

    @patch("os.path.isfile")
    @patch("builtins.open")
    @patch("find_usages.find_block._read_definition_code")
    def test_find_definitions_by_fqn(
        self, mock_read_code, mock_open, mock_isfile, mock_index_data
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )
        mock_read_code.return_value = "def test_func():\n    return True"

        # Call the function to find by fully qualified name
        result = find_definitions("module.test_func")

        # Verify results
        assert len(result) == 1
        assert result[0]["name"] == "test_func"
        assert result[0]["file"] == "test.py"
        assert result[0]["code"] == "def test_func():\n    return True"

    @patch("os.path.isfile")
    @patch("builtins.open")
    def test_find_definitions_without_code(
        self, mock_open, mock_isfile, mock_index_data
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )

        # Call the function with include_code=False
        result = find_definitions("TestClass", include_code=False)

        # Verify results
        assert len(result) == 2
        assert "code" not in result[0]
        assert "code" not in result[1]

    @patch("os.path.isfile")
    @patch("builtins.open")
    @patch("find_usages.find_block._read_definition_code")
    def test_find_definitions_code_not_found(
        self, mock_read_code, mock_open, mock_isfile, mock_index_data
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )
        mock_read_code.return_value = None  # Code could not be read

        # Call the function
        result = find_definitions("TestClass")

        # Verify results - code should be empty string when reading fails
        assert len(result) == 2
        assert result[0]["code"] == ""
