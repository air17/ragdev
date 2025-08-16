import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_tools.grep import search_codebase


def test_search_codebase_smoke():
    """Test that search_codebase runs without errors and returns expected format."""
    # Create a temporary directory with a test file
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test file with some content
        test_file = Path(temp_dir) / "example.py"
        test_content = """
        def example_function():
            return "This is a test function"

        class TestClass:
            pass
        """
        test_file.write_text(test_content)

        # Test searching for content we know exists
        result = search_codebase("example_function", str(temp_dir))

        # Basic assertions about the result
        assert isinstance(result, str)
        assert "example.py" in result
        assert "example_function" in result

        # Test with a pattern that shouldn't match anything
        empty_result = search_codebase("nonexistent_pattern", str(temp_dir))
        assert empty_result == ""


@patch("agent_tools.grep.Ripgrepy")
def test_search_codebase_mocked(mock_ripgrepy):
    """Test search_codebase with mocked Ripgrepy for more controlled testing."""
    # Setup mock
    mock_instance = MagicMock()
    mock_run = MagicMock()
    mock_run.as_string = "mocked/file.py:10:    test line"

    # Chain the mock calls
    mock_instance.with_filename.return_value = mock_instance
    mock_instance.line_number.return_value = mock_instance
    mock_instance.glob.return_value = mock_instance
    mock_instance.run.return_value = mock_run
    mock_ripgrepy.return_value = mock_instance

    # Call the function
    result = search_codebase("test pattern")

    # Verify the result
    assert result == "mocked/file.py:10:    test line"

    # Verify Ripgrepy was called with the right arguments
    mock_ripgrepy.assert_called_once_with("test pattern", ".")
    mock_instance.with_filename.assert_called_once()
    mock_instance.line_number.assert_called_once()
    assert mock_instance.glob.call_count >= 4  # Should be called for each glob pattern
