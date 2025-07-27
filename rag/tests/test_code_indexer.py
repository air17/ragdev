from unittest.mock import patch, MagicMock

from rag.code_indexer import process_directory, index
from rag.embeddings import EmbeddingManager


def test_process_directory_exists():
    """Check that the process_directory function exists and can be called."""
    # Just verify the function exists and has the expected signature
    assert callable(process_directory)

    # Create a mock manager
    mock_manager = MagicMock(spec=EmbeddingManager)

    # Patch necessary dependencies to prevent actual file system access
    with (
        patch("os.path.abspath"),
        patch("os.walk"),
        patch("builtins.open"),
        patch("rag.code_indexer.chunk_file"),
    ):
        # Call with minimal arguments to verify it doesn't throw exceptions
        process_directory(mock_manager)


def test_index_exists():
    """Check that index function exists and can be called."""
    # Verify the function exists and has the expected signature
    assert callable(index)

    # Patch dependencies to prevent actual operations
    with (
        patch("rag.code_indexer.EmbeddingManager") as mock_manager_class,
        patch("rag.code_indexer.process_directory"),
    ):
        # Setup the manager mock
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.create_collection_if_not_exists.return_value = True

        # Call with minimal arguments to verify it doesn't throw exceptions
        index()
