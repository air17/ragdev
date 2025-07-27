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
        assert len(result) == 3  # Class definition + 2 methods

        # Find the class definition chunk
        class_chunks = [chunk for chunk in result if chunk["type"] == "ClassDef"]
        assert len(class_chunks) == 1
        assert class_chunks[0]["start"] == 1
        assert class_chunks[0]["end"] == 1  # Only includes class declaration line

        # Find method chunks
        method_chunks = [chunk for chunk in result if chunk["type"] == "Method"]
        assert len(method_chunks) == 2

        # __init__ method
        init_method = next(c for c in method_chunks if c["start"] == 2)
        assert init_method["end"] == 3

        # get_value method
        get_value_method = next(c for c in method_chunks if c["start"] == 5)
        assert get_value_method["end"] == 6

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
        # Note: Import statements are skipped, so the block starts at the first non-import statement
        assert block_chunks[0]["start"] == 5  # MAX_VALUE constant (line 5)
        assert block_chunks[0]["end"] == 6  # Last constant definition

        # Find the function chunk
        func_chunks = [chunk for chunk in result if chunk["type"] == "FunctionDef"]
        assert len(func_chunks) == 1
        assert func_chunks[0]["start"] == 8  # Function definition starts
        assert func_chunks[0]["end"] == 9  # Function ends

    @patch("builtins.open")
    def test_chunk_file_class_with_attributes(self, mock_file):
        # Mock file with a class that has both attributes and methods
        mock_content = (
            "class ConfigClass:\n"
            "    # Class with attributes and methods\n"
            "    DEFAULT_SIZE = 100\n"
            "    MIN_VALUE = 0\n\n"
            "    def get_config(self):\n"
            "        return {\n"
            "            'size': self.DEFAULT_SIZE,\n"
            "            'min': self.MIN_VALUE\n"
            "        }\n"
        )
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function
        result = chunk_file("test.py")

        # Verify result
        assert len(result) == 2  # Class definition (with attributes) + 1 method

        # Find the class definition chunk
        class_chunks = [chunk for chunk in result if chunk["type"] == "ClassDef"]
        assert len(class_chunks) == 1
        assert class_chunks[0]["start"] == 1
        assert class_chunks[0]["end"] == 4  # Includes attributes

        # Find method chunks
        method_chunks = [chunk for chunk in result if chunk["type"] == "Method"]
        assert len(method_chunks) == 1
        assert method_chunks[0]["start"] == 6  # Method starts at line 6
        assert method_chunks[0]["end"] == 10  # Method ends at line 10

    @patch("builtins.open")
    def test_chunk_file_class_no_methods(self, mock_file):
        # Mock file with a class that has only attributes, no methods
        mock_content = (
            "class Constants:\n"
            '    """A class that only contains constants"""\n'
            "    PI = 3.14159\n"
            "    GRAVITY = 9.8\n"
            "    PLANCK = 6.62607015e-34\n"
        )
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function
        result = chunk_file("test.py")

        # Verify result
        assert len(result) == 1  # Only class definition, no methods

        # Check class chunk
        assert result[0]["type"] == "ClassDef"
        assert result[0]["start"] == 1
        assert result[0]["end"] == 5  # Includes all class contents

    @patch("builtins.open")
    def test_chunk_file_class_with_large_method(self, mock_file):
        # Create a class with a method that exceeds max_func_lines
        lines = ["class Calculator:\n", "    def calculate_large(self):\n"]
        for i in range(60):  # Create a method with 60+ lines
            lines.append(f"        print('Calculation step {i}')\n")
        lines.append("        return 42\n")

        mock_content = "".join(lines)
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function with default max_func_lines=50
        result = chunk_file("test.py")

        # Verify result
        assert len(result) == 3  # Class definition + 2 method chunks (split)

        # Check class definition
        class_chunks = [chunk for chunk in result if chunk["type"] == "ClassDef"]
        assert len(class_chunks) == 1
        assert class_chunks[0]["start"] == 1
        assert class_chunks[0]["end"] == 1  # Only class declaration line

        # Check method chunks - should be split into two
        method_chunks = [chunk for chunk in result if chunk["type"] == "Method"]
        assert len(method_chunks) == 2

        # Method chunks should cover all lines of the method
        method_start = method_chunks[0]["start"]
        method_end = method_chunks[1]["end"]
        assert method_start == 2  # Method starts at line 2
        assert method_end == 63  # Method ends at line 63

    @patch("builtins.open")
    def test_chunk_file_imports_only(self, mock_file):
        # Mock file with only import statements
        mock_content = (
            "import os\n"
            "import sys\n"
            "from typing import List, Dict, Optional\n"
            "import numpy as np\n"
        )
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function
        result = chunk_file("test.py")

        # Verify result - all imports should be skipped
        assert len(result) == 0

    @patch("builtins.open")
    def test_chunk_file_mixed_content(self, mock_file):
        # Mock file with mixed content: imports, constants, and multiple small blocks
        mock_content = (
            "import os\n"  # Import (skipped)
            "import sys\n\n"  # Import (skipped)
            "# Constants block 1\n"
            "PI = 3.14159\n"
            "E = 2.71828\n\n"
            "# Constants block 2\n"
            "GRAVITY = 9.8\n"
            "LIGHT_SPEED = 299792458\n\n"
            "def calculate(x):\n"
            "    return x * PI\n\n"
            "# More constants\n"
            "MAX_VALUE = 100\n"
        )
        mock_file.return_value.__enter__.return_value.read.return_value = mock_content

        # Call the function with default max_lines=30
        result = chunk_file("test.py")

        # Verify result
        assert len(result) == 3  # Two block chunks and one function chunk

        # Function chunk
        func_chunks = [chunk for chunk in result if chunk["type"] == "FunctionDef"]
        assert len(func_chunks) == 1
        assert func_chunks[0]["start"] == 12  # Function definition starts at line 12
        assert func_chunks[0]["end"] == 13  # Function ends at line 13

        # Block chunks (non-imports)
        block_chunks = [chunk for chunk in result if chunk["type"] == "Block"]
        assert len(block_chunks) == 2

        # First block - constants block 1 and 2
        first_block = next(c for c in block_chunks if c["start"] == 5)
        assert first_block["end"] == 10

        # Second block - more constants
        # Properly find the second block by filtering out the first block
        second_block = [c for c in block_chunks if c != first_block][0]
        assert second_block["start"] == 16  # Comment line
        assert second_block["end"] == 16
