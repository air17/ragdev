import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from rag.embeddings import (
    EmbeddingManager,
    MilvusInsertData,
    CODE_RETRIEVAL_QUERY_TASK_TYPE,
    RETRIEVAL_DOCUMENT_TASK_TYPE,
)


@pytest.fixture
def mock_milvus_client():
    with patch("rag.embeddings.MilvusClient") as mock:
        client_instance = MagicMock()
        mock.return_value = client_instance
        yield client_instance


@pytest.fixture
def mock_genai_client():
    with patch("rag.embeddings.GenAIClient") as mock:
        client_instance = MagicMock()
        mock.return_value = client_instance
        yield client_instance


@pytest.fixture
def embedding_manager(mock_milvus_client, mock_genai_client):
    return EmbeddingManager(
        milvus_endpoint="test_endpoint",
        milvus_token="test_token",
        gemini_api_key="test_key",
        collection_name="test_collection",
        vector_dimension=768,
    )


class TestEmbeddingManager:
    def test_initialization(
        self, embedding_manager, mock_milvus_client, mock_genai_client
    ):
        assert embedding_manager.milvus == mock_milvus_client
        assert embedding_manager.gemini == mock_genai_client
        assert embedding_manager.collection_name == "test_collection"

    def test_drop_collection(self, embedding_manager, mock_milvus_client):
        embedding_manager.drop_collection()
        mock_milvus_client.drop_collection.assert_called_once_with(
            collection_name="test_collection"
        )

    def test_create_collection_if_not_exists_exists(
        self, embedding_manager, mock_milvus_client
    ):
        # Setup mock to indicate collection exists
        mock_milvus_client.list_collections.return_value = ["test_collection"]

        # Call the function
        result = embedding_manager.create_collection_if_not_exists()

        # Verify result and that create_collection was not called
        assert result is False
        mock_milvus_client.create_collection.assert_not_called()

    def test_create_collection_if_not_exists_new(
        self, embedding_manager, mock_milvus_client
    ):
        # Setup mock to indicate collection doesn't exist
        mock_milvus_client.list_collections.return_value = ["other_collection"]

        # Call the function
        result = embedding_manager.create_collection_if_not_exists()

        # Verify result and that create_collection was called
        assert result is True
        mock_milvus_client.create_collection.assert_called_once()
        mock_milvus_client.load_collection.assert_called_once_with("test_collection")

    def test_get_embedding(self, embedding_manager, mock_genai_client):
        # Setup mock embedding response
        embedding_values = [0.1, 0.2, 0.3]
        embedding_obj = MagicMock()
        embedding_obj.values = embedding_values
        mock_genai_client.models.embed_content.return_value.embeddings = [embedding_obj]

        # Calculate expected normalized values manually
        np_array = np.array(embedding_values)
        expected_norm = (np_array / np.linalg.norm(np_array)).tolist()

        # Call the function
        result = embedding_manager.get_embedding("test text")

        # Verify result
        assert result == expected_norm
        mock_genai_client.models.embed_content.assert_called_once()

    def test_insert_embedding(self, embedding_manager, mock_milvus_client):
        # Mock data
        vector = [0.1, 0.2, 0.3]
        filename = "test.py"
        start_line = 10
        end_line = 20

        # Call the function
        embedding_manager.insert_embedding(vector, filename, start_line, end_line)

        # Verify Milvus insert was called with correct data
        mock_milvus_client.insert.assert_called_once_with(
            collection_name="test_collection",
            data=[
                MilvusInsertData(
                    vector=vector,
                    filename=filename,
                    start_line=start_line,
                    end_line=end_line,
                )
            ],
        )

    def test_add_to_vector(self, embedding_manager):
        # Mock the component methods
        embedding_manager.get_embedding = MagicMock(return_value=[0.1, 0.2, 0.3])
        embedding_manager.insert_embedding = MagicMock()

        # Call the function
        embedding_manager.add_to_vector("test content", "test.py", 10, 20)

        # Verify methods were called correctly
        embedding_manager.get_embedding.assert_called_once_with(
            "test content", RETRIEVAL_DOCUMENT_TASK_TYPE
        )
        embedding_manager.insert_embedding.assert_called_once_with(
            vector=[0.1, 0.2, 0.3], filename="test.py", start_line=10, end_line=20
        )

    def test_retrieve_vectors_for_question(self, embedding_manager, mock_milvus_client):
        # Mock the get_embedding method
        embedding_manager.get_embedding = MagicMock(return_value=[0.1, 0.2, 0.3])

        # Setup mock search results
        mock_search_results = [[{"id": 1, "distance": 0.9}]]
        mock_milvus_client.search.return_value = mock_search_results

        # Call the function
        result = embedding_manager.retrieve_vectors_for_question(
            "test question", top_k=5
        )

        # Verify methods were called correctly
        embedding_manager.get_embedding.assert_called_once_with(
            "test question", CODE_RETRIEVAL_QUERY_TASK_TYPE
        )
        mock_milvus_client.load_collection.assert_called_once_with("test_collection")
        mock_milvus_client.search.assert_called_once_with(
            collection_name="test_collection",
            data=[[0.1, 0.2, 0.3]],
            output_fields=["filename", "start_line", "end_line"],
            limit=5,
        )
        assert result == mock_search_results[0]
