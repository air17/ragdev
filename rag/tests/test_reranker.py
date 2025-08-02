import pytest
from unittest.mock import patch

from langchain_core.documents import Document

from rag.reranker import rerank_results, _results_to_documents


class TestReranking:
    """
    Test suite for the rerank_results function and related helper functions.

    This class contains tests for the document reranking functionality that uses
    LLMListwiseRerank with ChatDeepSeek to reorder search results based on relevance
    to a query.
    """

    @pytest.fixture
    def mock_enriched_search_results(self):
        """
        Create mock EnrichedSearchResult objects for testing.

        Returns:
            list: A list of dictionaries representing EnrichedSearchResult objects
                 with the necessary fields (id, distance, entity, snippet).
        """
        return [
            {
                "id": 1,
                "distance": 0.8,
                "entity": {
                    "filename": "file1.py",
                    "start_line": 10,
                    "end_line": 20,
                },
                "snippet": "def function1():\n    return 'result1'",
            },
            {
                "id": 2,
                "distance": 0.6,
                "entity": {
                    "filename": "file2.py",
                    "start_line": 5,
                    "end_line": 15,
                },
                "snippet": "def function2():\n    return 'result2'",
            },
            {
                "id": 3,
                "distance": 0.9,
                "entity": {
                    "filename": "file3.py",
                    "start_line": 1,
                    "end_line": 5,
                },
                "snippet": "def function3():\n    return 'result3'",
            },
        ]

    def test_results_to_documents(self, mock_enriched_search_results):
        """
        Test the _results_to_documents helper function.

        This test verifies that the _results_to_documents function correctly converts
        a list of EnrichedSearchResult objects into a list of Document objects.
        Each Document should have:
        - page_content set to the snippet from the original result
        - metadata containing the index of the original result as 'id'

        Args:
            mock_enriched_search_results: Fixture providing mock search results
        """
        documents = _results_to_documents(mock_enriched_search_results)

        assert len(documents) == 3
        assert isinstance(documents[0], Document)
        assert documents[0].page_content == "def function1():\n    return 'result1'"
        assert documents[0].metadata == {"id": 0}
        assert documents[1].page_content == "def function2():\n    return 'result2'"
        assert documents[1].metadata == {"id": 1}
        assert documents[2].page_content == "def function3():\n    return 'result3'"
        assert documents[2].metadata == {"id": 2}

    @patch("rag.reranker.LLMListwiseRerank")
    @patch("rag.reranker.ChatDeepSeek")
    def test_rerank_results_basic(
        self, mock_chat_deepseek, mock_reranker, mock_enriched_search_results
    ):
        """
        Test basic functionality of rerank_results with valid inputs.

        This test verifies that:
        1. The function correctly initializes ChatDeepSeek and LLMListwiseRerank
        2. It passes the documents and query to the reranker's compress_documents method
        3. It correctly maps the reranked documents back to the original search results
        4. The returned results are in the expected order based on the reranking

        Args:
            mock_chat_deepseek: Mocked ChatDeepSeek class
            mock_reranker: Mocked LLMListwiseRerank class
            mock_enriched_search_results: Fixture providing mock search results
        """
        # Set up mocks
        mock_llm_instance = mock_chat_deepseek.return_value
        mock_reranker_instance = mock_reranker.from_llm.return_value

        # Create mock reranked documents (in a different order than the original)
        mock_reranked_docs = [
            Document(
                page_content="def function2():\n    return 'result2'",
                metadata={"id": 1},
            ),
            Document(
                page_content="def function3():\n    return 'result3'",
                metadata={"id": 2},
            ),
            Document(
                page_content="def function1():\n    return 'result1'",
                metadata={"id": 0},
            ),
        ]
        mock_reranker_instance.compress_documents.return_value = mock_reranked_docs

        # Call the function
        query = "test query"
        result = rerank_results(query, mock_enriched_search_results)

        # Verify the function behavior
        mock_chat_deepseek.assert_called_once_with(model="deepseek-chat")
        mock_reranker.from_llm.assert_called_once_with(llm=mock_llm_instance, top_n=3)
        mock_reranker_instance.compress_documents.assert_called_once()

        # Check that the results are in the expected order
        assert len(result) == 3
        assert (
            result[0] == mock_enriched_search_results[1]
        )  # Second result should be first
        assert (
            result[1] == mock_enriched_search_results[2]
        )  # Third result should be second
        assert (
            result[2] == mock_enriched_search_results[0]
        )  # First result should be third

    @patch("rag.reranker.LLMListwiseRerank")
    @patch("rag.reranker.ChatDeepSeek")
    def test_rerank_results_max_results(
        self, mock_chat_deepseek, mock_reranker, mock_enriched_search_results
    ):
        """
        Test rerank_results with a custom max_results parameter.

        This test verifies that:
        1. The max_results parameter is correctly passed to the LLMListwiseRerank constructor
        2. The function returns only the specified number of results
        3. The returned results are in the correct order based on the reranking

        Args:
            mock_chat_deepseek: Mocked ChatDeepSeek class
            mock_reranker: Mocked LLMListwiseRerank class
            mock_enriched_search_results: Fixture providing mock search results
        """
        # Set up mocks
        mock_llm_instance = mock_chat_deepseek.return_value
        mock_reranker_instance = mock_reranker.from_llm.return_value

        # Create mock reranked documents (only 2 as per max_results)
        mock_reranked_docs = [
            Document(
                page_content="def function2():\n    return 'result2'",
                metadata={"id": 1},
            ),
            Document(
                page_content="def function1():\n    return 'result1'",
                metadata={"id": 0},
            ),
        ]
        mock_reranker_instance.compress_documents.return_value = mock_reranked_docs

        # Call the function with max_results=2
        query = "test query"
        result = rerank_results(query, mock_enriched_search_results, max_results=2)

        # Verify the function behavior
        mock_chat_deepseek.assert_called_once_with(model="deepseek-chat")
        mock_reranker.from_llm.assert_called_once_with(llm=mock_llm_instance, top_n=2)
        mock_reranker_instance.compress_documents.assert_called_once()

        # Check that the results are in the expected order and only 2 results are returned
        assert len(result) == 2
        assert (
            result[0] == mock_enriched_search_results[1]
        )  # Second result should be first
        assert (
            result[1] == mock_enriched_search_results[0]
        )  # First result should be second

    @patch("rag.reranker.LLMListwiseRerank")
    @patch("rag.reranker.ChatDeepSeek")
    def test_rerank_results_empty_list(self, mock_chat_deepseek, mock_reranker):
        """
        Test rerank_results with an empty list of search results.

        This test verifies that:
        1. The function handles an empty list of search results gracefully
        2. The function still initializes the LLM and reranker correctly
        3. The function returns an empty list when given an empty list

        This is an important edge case to test as it ensures the function
        doesn't throw exceptions when no search results are available.

        Args:
            mock_chat_deepseek: Mocked ChatDeepSeek class
            mock_reranker: Mocked LLMListwiseRerank class
        """
        # Set up mocks
        mock_llm_instance = mock_chat_deepseek.return_value
        mock_reranker_instance = mock_reranker.from_llm.return_value
        mock_reranker_instance.compress_documents.return_value = []

        # Call the function with an empty list
        query = "test query"
        result = rerank_results(query, [])

        # Verify the function behavior
        mock_chat_deepseek.assert_called_once_with(model="deepseek-chat")
        mock_reranker.from_llm.assert_called_once_with(llm=mock_llm_instance, top_n=3)
        mock_reranker_instance.compress_documents.assert_called_once()

        # Check that an empty list is returned
        assert result == []
