"""Main convenience module.

Provides high-level wrappers for both the vector-based RAG index (Milvus/Gemini)
from ``rag.code_indexer`` and the static symbol usage index from
``find_usages``.  This makes it easy to build the two indices in one step and
query either of them without having to remember the lower-level API surface.
"""

import os
from typing import List, Dict, Any

from config import DEFAULT_COLLECTION_NAME
from rag.embeddings import EmbeddingManager
from rag.code_indexer import index as _vector_index
from find_usages.indexer import index_project as _usages_index
from find_usages.finder import UsageRecord, find_usages as _find_usages

__all__ = [
    "index_all",
    "search_code",
    "find_symbol_usages",
]


def index_all(directory: str | os.PathLike[str] = ".") -> None:
    """Index *directory* with both available back-ends.

    This helper simply forwards to :pyfunc:`rag.code_indexer.index` to create
    the vector database and to :pyfunc:`find_usages.indexer.index_project` to
    create the static symbol usage index.

    Parameters
    ----------
    directory:
        Path to the root of the project whose source files should be indexed.
        *Default* is the current working directory.
    """

    # Ensure we work with a string path
    directory_str = os.fspath(directory)

    print("\n[1/2] Building vector index (Milvus/Gemini)…")
    _vector_index(directory_str)

    print("\n[2/2] Building usages index (Jedi)…")
    _usages_index(directory_str)

    print("\n✔ Indexing completed.")


def search_code(
    question: str,
    *,
    top_k: int = 5,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> List[Dict[str, Any]]:
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
    list[dict]
        A list of result dictionaries as returned by Milvus.  Each dictionary
        contains at least ``filename``, ``start_line`` and ``end_line`` keys
        plus the similarity ``score``.
    """

    manager = EmbeddingManager(collection_name=collection_name)
    # The Milvus Python SDK wraps results in a nested list where index 0 is the
    # list of hits for our single query vector.  We flatten it for convenience.
    results_nested = manager.retrieve_vectors_for_question(question, top_k=top_k)
    return results_nested[0] if results_nested else []


def find_symbol_usages(
    root: str | os.PathLike[str],
    target: str,
    *,
    index_file: str = "usages_index.json",
) -> List[UsageRecord]:
    """Find every occurrence of *target* inside *root*.

    Wrapper around :pyfunc:`find_usages.finder.find_usages`.

    Parameters
    ----------
    root:
        Directory that was previously indexed with :pyfunc:`index_all` (or
        :pyfunc:`find_usages.indexer.index_project`).
    target:
        Simple name (``"SomeClass"``) or fully-qualified name
        (``"package.module.SomeClass"``) of the symbol we are looking for.
    index_file:
        Path to the JSON index file created by the indexing process.  Defaults
        to ``"usages_index.json"`` in the current directory.

    Returns
    -------
    list[UsageRecord]
        One entry per usage location.
    """

    root_str = os.fspath(root)
    return _find_usages(root_str, target=target, index_file=index_file)
