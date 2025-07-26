"""rag.snippet_reader
=====================
Utility to extract code snippets from files based on search-result metadata.

Typical search-result element::

    {
        "id": 459604326231119371,
        "distance": 0.7433037757873535,
        "entity": {
            "filename": "main.py",
            "start_line": 25,
            "end_line": 48
        }
    }

The :func:`read_snippets` helper below reads *filename* between *start_line* and
*end_line* (inclusive) for each entry and returns a list of dictionaries with
an additional ``snippet`` key that holds the extracted text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Union, TypedDict


class SearchResultEntity(TypedDict):
    """Entity data in a search result."""

    filename: str
    start_line: int
    end_line: int


class SearchResult(TypedDict):
    """Search result from vector database."""

    id: int
    distance: float
    entity: SearchResultEntity


class EnrichedSearchResult(SearchResult):
    """Search result enriched with code snippet."""

    snippet: str


__all__ = ["read_snippets"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_single_snippet(file_path: Path, start: int, end: int) -> str:
    """Return text contained in *file_path* between *start* and *end* lines.

    Lines are **1-indexed**; *end* is inclusive.
    If the file cannot be opened or the range is invalid, an empty string
    is returned.
    """
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return ""

    # Clamp range to file length and valid values
    start = max(1, start)
    end = min(len(lines), end)
    if start > end:
        return ""

    # Convert to 0-indexed slice; *end* is inclusive so use end
    return "".join(lines[start - 1 : end])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_snippets(
    matches: Iterable[SearchResult], *, base_dir: Union[str, Path, None] = None
) -> list[EnrichedSearchResult]:
    """Return *matches* augmented with the corresponding code snippets.

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

        snippet = _read_single_snippet(
            path,
            int(entity.get("start_line", 1)),
            int(entity.get("end_line", 0)),
        )
        if snippet:
            # Create a copy of the original item as a dict
            new_item_dict = dict(item)
            # Add the snippet
            new_item_dict["snippet"] = snippet
            # Convert to EnrichedSearchResult
            enriched_results.append(new_item_dict)  # Type coercion happens here

    return enriched_results
