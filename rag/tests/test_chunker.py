from unittest.mock import patch

from rag.chunker import chunk_file


class TestChunker:
    @patch("builtins.open")
    def test_chunk_file_empty(self, mock_file):
        # Setup mock file with empty content
        mock_file.return_value.__enter__.return_value.read.return_value = ""

        # Call the function
        result = chunk_file("test.py")

        # Verify result
        assert result == []

    @patch("builtins.open")
    def test_chunk_file_simple_function(self, mock_file):
        # Mock file with a simple function
        mock_content = "def test_func():\n    print('Hello')\n    return True\n"
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function
        result = chunk_file("test.py")

        # Verify result
        assert len(result) == 1
        assert result[0]["type"] == "FunctionDef"
        assert result[0]["start"] == 1
        assert result[0]["end"] == 3

    @patch("builtins.open")
    def test_chunk_file_class(self, mock_file):
        # Mock file with a class
        mock_content = (
            "class TestClass:\n"
            "    def __init__(self):\n"
            "        self.value = 42\n"
            "\n"
            "    def get_value(self):\n"
            "        return self.value\n"
        )
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function
        result = chunk_file("test.py")

        # Verify result
        assert len(result) == 1
        assert result[0]["type"] == "ClassDef"
        assert result[0]["start"] == 1
        assert result[0]["end"] == 6

    @patch("builtins.open")
    def test_chunk_file_large_function(self, mock_file):
        # Create a large function that exceeds max_func_lines
        lines = ["def large_function():\n"]
        for i in range(60):  # Create a function with 61 lines total
            lines.append(f"    print('Line {i}')\n")

        mock_content = "".join(lines)
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function with default max_func_lines=50
        result = chunk_file("test.py")

        # Verify result - should be split into two chunks
        assert len(result) == 2
        assert result[0]["type"] == "FunctionDef"
        assert result[1]["type"] == "FunctionDef"

        # First chunk should start at line 1
        assert result[0]["start"] == 1

        # Second chunk should end at line 61
        assert result[1]["end"] == 61

    @patch("builtins.open")
    def test_chunk_file_blocks(self, mock_file):
        # Mock file with multiple top-level statements
        mock_content = (
            "import os\n"
            "import sys\n\n"
            "# Some constants\n"
            "MAX_VALUE = 100\n"
            "MIN_VALUE = 0\n\n"
            "def test_func():\n"
            "    return True\n"
        )
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function
        result = chunk_file("test.py")

        # Verify result
        assert len(result) == 2  # One block chunk and one function chunk

        # Find the block chunk
        block_chunks = [chunk for chunk in result if chunk["type"] == "Block"]
        assert len(block_chunks) == 1
        assert block_chunks[0]["start"] == 1  # First line
        assert block_chunks[0]["end"] == 6  # Last constant definition

        # Find the function chunk
        func_chunks = [chunk for chunk in result if chunk["type"] == "FunctionDef"]
        assert len(func_chunks) == 1
        assert func_chunks[0]["start"] == 8  # Function definition starts
        assert func_chunks[0]["end"] == 9  # Function ends
