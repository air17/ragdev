import pytest
import tempfile
import os
import shutil
from unittest.mock import patch

from agent_tools.file_list import search_files_recursive


@pytest.fixture
def test_directory():
    """Create a temporary directory with test files for testing."""
    test_dir = tempfile.mkdtemp()

    # Create test files and directories
    test_files = [
        "file1.txt",
        "file2.py",
        "subdir1/file3.txt",
        "subdir1/file4.py",
        "subdir1/subdir2/file5.txt",
        "subdir1/subdir2/file6.log",
        "another.md",
    ]

    for file_path in test_files:
        full_path = os.path.join(test_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(f"Content of {file_path}")

    yield test_dir

    # Cleanup
    shutil.rmtree(test_dir)


@pytest.fixture
def empty_directory():
    """Create an empty temporary directory for testing."""
    empty_dir = tempfile.mkdtemp()
    yield empty_dir
    shutil.rmtree(empty_dir)


def test_find_txt_files(test_directory):
    """Test finding all .txt files recursively."""
    result = search_files_recursive("*.txt", test_directory)

    assert "Found 3 file(s)" in result
    assert "*.txt" in result
    assert "file1.txt" in result
    assert "subdir1/file3.txt" in result
    assert "subdir1/subdir2/file5.txt" in result
    assert "file2.py" not in result


def test_find_py_files(test_directory):
    """Test finding all .py files recursively."""
    result = search_files_recursive("*.py", test_directory)

    assert "Found 2 file(s)" in result
    assert "*.py" in result
    assert "file2.py" in result
    assert "subdir1/file4.py" in result
    assert "file1.txt" not in result


def test_no_files_found(test_directory):
    """Test when no files match the pattern."""
    result = search_files_recursive("*.nonexistent", test_directory)

    expected = f"No files found matching pattern '*.nonexistent' in directory '{test_directory}'"
    assert result == expected


def test_wildcard_pattern(test_directory):
    """Test using wildcard patterns."""
    result = search_files_recursive("file*", test_directory)

    assert "Found" in result
    assert "file1.txt" in result
    assert "file2.py" in result
    assert "subdir1/file3.txt" in result
    assert "subdir1/file4.py" in result
    assert "subdir1/subdir2/file5.txt" in result
    assert "subdir1/subdir2/file6.log" in result
    assert "another.md" not in result


def test_default_directory(test_directory):
    """Test using default directory (current directory)."""
    # Change to test directory and run the function
    original_cwd = os.getcwd()
    try:
        os.chdir(test_directory)
        result = search_files_recursive("*.txt")
        assert "Found" in result
        assert "file1.txt" in result
    finally:
        os.chdir(original_cwd)


def test_nonexistent_directory():
    """Test with non-existent directory."""
    result = search_files_recursive("*.txt", "/nonexistent/directory")

    expected = (
        "No files found matching pattern '*.txt' in directory '/nonexistent/directory'"
    )
    assert result == expected


def test_empty_directory(empty_directory):
    """Test with empty directory."""
    result = search_files_recursive("*.txt", empty_directory)
    expected = (
        f"No files found matching pattern '*.txt' in directory '{empty_directory}'"
    )
    assert result == expected


def test_result_format(test_directory):
    """Test the format of the result string."""
    result = search_files_recursive("*.txt", test_directory)

    lines = result.split("\n")
    # First line should contain summary
    assert "Found" in lines[0] and "file(s) matching pattern" in lines[0]

    # Subsequent lines should be numbered and contain file info
    for i, line in enumerate(lines[1:], 1):
        if line.strip():  # Skip empty lines
            assert f"{i}." in line
            assert "bytes)" in line


def test_file_sizes_included(test_directory):
    """Test that file sizes are included in the output."""
    result = search_files_recursive("*.txt", test_directory)

    # Should contain byte information
    assert "bytes)" in result
    # Should contain numbers for file sizes
    import re

    assert re.search(r"\(\d+ bytes\)", result)


def test_relative_paths(test_directory):
    """Test that relative paths are used in output."""
    result = search_files_recursive("*.txt", test_directory)

    # Should not contain the full test directory path in file listings
    lines = result.split("\n")[1:]  # Skip summary line
    for line in lines:
        if line.strip() and not line.startswith("No files"):
            # Extract file path (between number and byte count)
            path_part = line.split(" (")[0].split(". ", 1)[1]
            assert not path_part.startswith(test_directory)


@patch("os.path.getsize")
@patch("os.path.exists")
def test_file_size_error_handling(mock_exists, mock_getsize, test_directory):
    """Test handling when file size cannot be determined."""
    mock_exists.return_value = True  # Files exist
    mock_getsize.side_effect = OSError("File not accessible")

    result = search_files_recursive("*.txt", test_directory)

    # Should still work and show 0 bytes for files with size errors
    assert "Found" in result
    assert "(0 bytes)" in result


@pytest.mark.parametrize(
    "pattern,expected_count",
    [("*.txt", 3), ("*.py", 2), ("*.log", 1), ("*.md", 1), ("file*", 6), ("*.xyz", 0)],
)
def test_various_patterns(test_directory, pattern, expected_count):
    """Test various glob patterns with parameterized testing."""
    result = search_files_recursive(pattern, test_directory)

    if expected_count == 0:
        assert "No files found" in result
    else:
        assert f"Found {expected_count} file(s)" in result


def test_nested_subdirectories(test_directory):
    """Test that files in nested subdirectories are found."""
    result = search_files_recursive("*.txt", test_directory)

    # Should find files at different nesting levels
    assert "file1.txt" in result  # Root level
    assert "subdir1/file3.txt" in result  # One level deep
    assert "subdir1/subdir2/file5.txt" in result  # Two levels deep


def test_custom_root_dir(test_directory):
    """Test using a custom root_dir different from search directory."""
    # Create a parent directory that contains test_directory
    parent_dir = tempfile.mkdtemp()
    try:
        # Move test_directory to be inside parent_dir
        test_subdir = os.path.join(parent_dir, "project")
        os.makedirs(test_subdir, exist_ok=True)

        # Create a test file in test_subdir
        test_file = os.path.join(test_subdir, "test_file.txt")
        with open(test_file, "w") as f:
            f.write("Test content")

        # Test with parent_dir as root_dir
        result = search_files_recursive("*.txt", test_subdir, root_dir=parent_dir)

        # Paths should be relative to parent_dir, not test_subdir
        assert "project/test_file.txt" in result
    finally:
        shutil.rmtree(parent_dir)
