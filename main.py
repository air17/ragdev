"""Main convenience module.

Provides high-level wrappers for the vector-based RAG index (Milvus/Gemini)
from ``rag.code_indexer``.
"""

import os

from config import DEFAULT_COLLECTION_NAME
from rag.embeddings import EmbeddingManager
from rag.code_indexer import index
from rag.snippet_reader import SearchResult, EnrichedSearchResult

__all__ = [
    "index_all",
    "search_code",
    "search_code_with_snippets",
]

from rag.snippet_reader import read_snippets


def index_all(directory: str | os.PathLike[str] = ".", resume: bool = True) -> None:
    """Index *directory* with both available back-ends.

    This helper simply forwards to :pyfunc:`rag.code_indexer.index` to create
    the vector database and to :pyfunc:`agent_tools.indexer.index_project` to
    create the static symbol usage index.

    Parameters
    ----------
    directory:
        Path to the root of the project whose source files should be indexed.
        *Default* is the current working directory.
    """

    # Ensure we work with a string path
    directory_str = os.fspath(directory)

    print("\nBuilding vector index (Milvus/Gemini)…")
    index(directory_str, resume=resume)

    print("\n✔ Indexing completed.")


def search_code(
    question: str,
    *,
    top_k: int = 5,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> list[SearchResult]:
    """Return *top_k* code chunks that best match *question*.

    This is a thin wrapper around
    :pyfunc:`rag.embeddings.EmbeddingManager.retrieve_vectors_for_question`.

    Parameters
    ----------
    question:
        Natural-language query.
    top_k:
        Maximum number of results to return.
    collection_name:
        Name of the Milvus collection to query.  Defaults to ``"ragdev"``.

    Returns
    -------
    list[SearchResult]
        A list of result dictionaries as returned by Milvus.  Each dictionary
        contains at least ``filename``, ``start_line`` and ``end_line`` keys
        plus the similarity ``score``.
    """

    manager = EmbeddingManager(collection_name=collection_name)
    # The Milvus Python SDK wraps results in a nested list where index 0 is the
    # list of hits for our single query vector.  We flatten it for convenience.
    return manager.retrieve_vectors_for_question(question, top_k=top_k)


def search_code_with_snippets(
    question: str,
    *,
    top_k: int = 5,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> list[EnrichedSearchResult]:
    """Return *top_k* code chunks that best match question, along with snippets."""
    return read_snippets(
        search_code(question, top_k=top_k, collection_name=collection_name)
    )
