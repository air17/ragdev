import warnings
from pathlib import Path
from typing import Iterable, Union

from agent_tools.read_file import read_file
from rag.embeddings import MilvusSearchResult as SearchResult


class EnrichedSearchResult(SearchResult, total=False):
    """Search result enriched with code snippet."""

    snippet: str


__all__ = ["read_snippets"]


def read_snippets(
    matches: Iterable[SearchResult], *, base_dir: Union[str, Path, None] = None
) -> list[EnrichedSearchResult]:
    """Return *matches* augmented with the corresponding code snippets.

    .. deprecated::
        This function is not used by ChatAgent and will be removed in a future version.

    Parameters
    ----------
    matches
        Iterable with search result entries. Each entry must contain an
        ``entity`` mapping with at least ``filename``, ``start_line`` and
        ``end_line`` keys.
    base_dir
        Optional directory prepended to relative file names. Useful when the
        search engine returns paths relative to the project root.

    Returns
    -------
    list of EnrichedSearchResult
        New list where each element is a **shallow copy** of the original
        entry plus a ``snippet`` field. Entries for which the snippet cannot
        be resolved are silently omitted.
    """
    root = Path(base_dir) if base_dir is not None else None
    warnings.warn(
        "read_snippets is deprecated. Milvus-based semantic search is no longer "
        "used by ChatAgent and will be removed in a future version.",
        DeprecationWarning,
        stacklevel=2,
    )
    enriched_results: list[EnrichedSearchResult] = []

    for item in matches:
        entity = item.get("entity", {})
        filename = entity.get("filename")
        if not filename:
            # Skip items without a file reference
            continue

        path = Path(filename)
        if root is not None and not path.is_absolute():
            path = root / path

        try:
            snippet: str = read_file(
                str(path),
                int(entity.get("start_line", 1)),
                int(entity.get("end_line")),
                add_line_numbers=True,
            )
        except FileNotFoundError:
            snippet = ""
        if snippet:
            # Create a copy of the original item as a dict
            new_item_dict = EnrichedSearchResult(item)
            # Add the snippet
            new_item_dict["snippet"] = snippet
            # Convert to EnrichedSearchResult
            enriched_results.append(new_item_dict)  # Type coercion happens here

    return enriched_results
