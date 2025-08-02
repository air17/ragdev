import pytest
from unittest.mock import patch, mock_open
import tempfile
import os

from agent_tools.read_file import read_file_with_context


# Assuming the function is in a module called 'agent_tools.read_file'
# from agent_tools.read_file import read_file_with_context


def test_empty_path():
    """Test that empty path raises ValueError."""
    with pytest.raises(ValueError, match="Path cannot be empty"):
        read_file_with_context("")


def test_invalid_start_line():
    """Test that start_line < 1 raises ValueError."""
    with pytest.raises(ValueError, match="start_line must be at least 1"):
        read_file_with_context("test.py", start_line=0)


def test_invalid_end_line():
    """Test that end_line < start_line raises ValueError."""
    with pytest.raises(ValueError, match="end_line must be >= start_line"):
        read_file_with_context("test.py", start_line=5, end_line=3)


@patch("builtins.open", new_callable=mock_open, read_data="   \n  \n\n")
@patch("agent_tools.read_file.extract_top_level_imports")
def test_empty_file(mock_extract, mock_file):
    """Test handling of empty file (only whitespace)."""
    mock_extract.return_value = ("", 0)

    result = read_file_with_context("empty.py")
    assert result == "Empty file"


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="print('hello')\nprint('world')\n",
)
@patch("agent_tools.read_file.extract_top_level_imports")
def test_simple_file_no_imports(mock_extract, mock_file):
    """Test reading a simple file with no imports."""
    mock_extract.return_value = ("", 0)

    result = read_file_with_context("simple.py")
    expected = "1: print('hello')\n2: print('world')\n"
    assert result == expected


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="import os\nimport sys\nprint('hello')\n",
)
@patch("agent_tools.read_file.extract_top_level_imports")
def test_file_with_imports_included_in_range(mock_extract, mock_file):
    """Test file with imports that are included in the requested range."""
    mock_extract.return_value = ("1: import os\n2: import sys\n", 2)

    result = read_file_with_context("with_imports.py", start_line=1, end_line=3)
    expected = "1: import os\n2: import sys\n3: print('hello')\n"
    assert result == expected


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="import os\nimport sys\nprint('hello')\nprint('world')\n",
)
@patch("agent_tools.read_file.extract_top_level_imports")
def test_file_with_imports_outside_range(mock_extract, mock_file):
    """Test file with imports outside the requested range."""
    mock_extract.return_value = ("1: import os\n2: import sys\n", 2)

    result = read_file_with_context("with_imports.py", start_line=3, end_line=4)
    expected = "# Imports from file:\n1: import os\n2: import sys\n\n\n3: print('hello')\n4: print('world')\n"
    assert result == expected


@patch("builtins.open", new_callable=mock_open)
@patch("agent_tools.read_file.extract_top_level_imports")
@patch("agent_tools.read_file.summarize_chunk")
def test_long_file_with_summaries(mock_summarize, mock_extract, mock_file):
    """Test file that requires summaries for before/after context."""
    # Create a file with 30 lines to ensure summaries are triggered
    lines = [f"line {i}\n" for i in range(1, 31)]
    mock_file.return_value.readlines.return_value = lines

    mock_extract.return_value = ("1: import os\n", 1)
    mock_summarize.side_effect = [
        "Summary of lines before main content",
        "Summary of lines after main content",
    ]

    result = read_file_with_context("long.py", start_line=15, end_line=17)

    # Should include imports, summary of lines 2-14 (13 lines > 10), main content 15-17, summary of lines 18-30 (13 lines > 10)
    assert "# Imports from file:" in result
    assert "1: import os" in result
    assert "Summary of lines 2-14:" in result
    assert "Summary of lines before main content" in result
    assert "15: line 15" in result
    assert "16: line 16" in result
    assert "17: line 17" in result
    assert "Summary of lines 18-30:" in result
    assert "Summary of lines after main content" in result


@patch("builtins.open", new_callable=mock_open)
@patch("agent_tools.read_file.extract_top_level_imports")
def test_short_context_inlined(mock_extract, mock_file):
    """Test that short context (<=10 lines) is inlined rather than summarized."""
    # Create a file with 15 lines
    lines = [f"line {i}\n" for i in range(1, 16)]
    mock_file.return_value.readlines.return_value = lines

    mock_extract.return_value = ("1: import os\n", 1)

    result = read_file_with_context("medium.py", start_line=6, end_line=10)

    # Lines 2-5 (4 lines) should be inlined, not summarized
    assert "2: line 2" in result
    assert "3: line 3" in result
    assert "4: line 4" in result
    assert "5: line 5" in result

    # Lines 11-15 (5 lines) should be inlined, not summarized
    assert "11: line 11" in result
    assert "15: line 15" in result

    # Should not contain summary text
    assert "Summary of" not in result


@patch("builtins.open", new_callable=mock_open, read_data="import os\nprint('hello')\n")
@patch("agent_tools.read_file.extract_top_level_imports")
def test_end_line_none(mock_extract, mock_file):
    """Test that end_line=None reads to end of file."""
    mock_extract.return_value = ("1: import os\n", 1)

    result = read_file_with_context("test.py", start_line=2, end_line=None)
    expected = "# Imports from file:\n1: import os\n\n\n2: print('hello')\n"
    assert result == expected


@patch("builtins.open", new_callable=mock_open, read_data="import os\nprint('hello')\n")
@patch("agent_tools.read_file.extract_top_level_imports")
def test_end_line_beyond_file(mock_extract, mock_file):
    """Test that end_line beyond file length is normalized."""
    mock_extract.return_value = ("1: import os\n", 1)

    result = read_file_with_context("test.py", start_line=2, end_line=100)
    expected = "# Imports from file:\n1: import os\n\n\n2: print('hello')\n"
    assert result == expected


@patch("builtins.open", new_callable=mock_open, read_data="import os\nimport sys\n")
@patch("agent_tools.read_file.extract_top_level_imports")
def test_start_line_adjusted_by_imports(mock_extract, mock_file):
    """Test that start_line is adjusted when it overlaps with imports."""
    mock_extract.return_value = ("1: import os\n2: import sys\n", 2)

    result = read_file_with_context("test.py", start_line=1, end_line=2)
    # When start_line overlaps with imports, it should be adjusted
    expected = "1: import os\n2: import sys\n"
    assert result == expected


def test_integration_with_real_file():
    """Integration test with a real temporary file."""
    content = """import os
import sys
from pathlib import Path

def main():
    print("Hello")
    return True

def helper():
    pass

if __name__ == "__main__":
    main()
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Mock the dependencies since they're not available
        with patch("agent_tools.read_file.extract_top_level_imports") as mock_extract:
            mock_extract.return_value = (
                "1: import os\n2: import sys\n3: from pathlib import Path\n",
                3,
            )

            result = read_file_with_context(temp_path, start_line=5, end_line=7)

            # Should include imports and the requested lines
            assert "# Imports from file:" in result
            assert "import os" in result
            assert "def main():" in result
            assert 'print("Hello")' in result
            assert "return True" in result

    finally:
        os.unlink(temp_path)
