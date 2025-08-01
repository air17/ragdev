import os
import pytest
import tempfile
from unittest.mock import patch, mock_open

from agent_tools.read_file import read_file


class TestReadFile:
    def test_read_file_entire_file(self):
        # Mock file content
        mock_content = "line1\nline2\nline3\n"

        # Use mock_open to simulate file reading
        with patch("builtins.open", mock_open(read_data=mock_content)):
            result = read_file("dummy_path.txt")

            # Verify the entire file is read
            assert result == mock_content

    def test_read_file_with_line_range(self):
        # Mock file content
        mock_content = "line1\nline2\nline3\nline4\nline5\n"

        # Use mock_open to simulate file reading
        with patch("builtins.open", mock_open(read_data=mock_content)):
            # Read lines 2-4
            result = read_file("dummy_path.txt", start_line=2, end_line=4)

            # Verify only specified lines are read
            assert result == "line2\nline3\nline4\n"

    def test_read_file_with_line_numbers(self):
        # Mock file content
        mock_content = "line1\nline2\nline3\n"

        # Use mock_open to simulate file reading
        with patch("builtins.open", mock_open(read_data=mock_content)):
            # Read with line numbers
            result = read_file("dummy_path.txt", add_line_numbers=True)

            # Verify line numbers are added
            assert result == "1: line1\n2: line2\n3: line3\n"

    def test_read_file_with_line_range_and_numbers(self):
        # Mock file content
        mock_content = "line1\nline2\nline3\nline4\nline5\n"

        # Use mock_open to simulate file reading
        with patch("builtins.open", mock_open(read_data=mock_content)):
            # Read lines 2-4 with line numbers
            result = read_file(
                "dummy_path.txt", start_line=2, end_line=4, add_line_numbers=True
            )

            # Verify only specified lines are read with line numbers
            assert result == "2: line2\n3: line3\n4: line4\n"

    def test_read_file_empty_file(self):
        # Mock empty file
        with patch("builtins.open", mock_open(read_data="")):
            result = read_file("empty_file.txt")

            # Verify empty string is returned
            assert result == ""

    def test_read_file_end_line_beyond_file_length(self):
        # Mock file content
        mock_content = "line1\nline2\nline3\n"

        # Use mock_open to simulate file reading
        with patch("builtins.open", mock_open(read_data=mock_content)):
            # Try to read beyond file end
            result = read_file("dummy_path.txt", end_line=10)

            # Verify all lines are read
            assert result == mock_content

    def test_read_file_with_real_file(self):
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write("line1\nline2\nline3\nline4\nline5\n")
            temp_path = temp_file.name

        try:
            # Read from the actual file
            result = read_file(temp_path, start_line=2, end_line=4)
            assert result == "line2\nline3\nline4\n"

            # Read with line numbers
            result = read_file(temp_path, add_line_numbers=True)
            assert result == "1: line1\n2: line2\n3: line3\n4: line4\n5: line5\n"
        finally:
            # Clean up
            os.unlink(temp_path)

    def test_read_file_empty_path(self):
        # Test with empty path
        with pytest.raises(ValueError, match="Path cannot be empty"):
            read_file("")

    def test_read_file_invalid_start_line(self):
        # Test with invalid start line
        with pytest.raises(ValueError, match="start_line must be at least 1"):
            read_file("dummy_path.txt", start_line=0)

    def test_read_file_end_line_less_than_start_line(self):
        # Test with end_line < start_line
        with pytest.raises(
            ValueError, match="end_line must be greater than or equal to start_line"
        ):
            read_file("dummy_path.txt", start_line=5, end_line=3)

    def test_read_file_start_line_exceeds_file_length(self):
        # Mock file content
        mock_content = "line1\nline2\nline3\n"

        # Use mock_open to simulate file reading
        with patch("builtins.open", mock_open(read_data=mock_content)):
            # Try to start reading beyond file end
            with pytest.raises(ValueError, match="start_line exceeds file length"):
                read_file("dummy_path.txt", start_line=5)
