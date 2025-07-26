"""
Utilities for quickly locating class / function / method definitions that
have been recorded by the indexer.  The indexer produces a simple
JSON file (``usages_index.json`` by default) that stores – for every symbol it
encounters – the symbol’s simple name, its fully–qualified name (FQN), source
file, and position in that file.

The helper(s) below make it easy to retrieve those definitions later on and,
optionally, return the exact source code for every match.
"""

import json
import os

from config import USAGES_INDEX_FILE
from find_usages.indexer import IndexEntry


class DefinitionRecord(IndexEntry, total=False):
    """
    A single definition entry returned by ``find_definitions``.
    The layout mirrors the structure written by the indexer with the addition
    of an optional ``code`` field containing the definition's source code.
    """

    # optional – filled only when `include_code=True`
    code: str


def _load_index(index_file: str | os.PathLike) -> list[IndexEntry]:
    """
    Load and return the raw JSON content produced by the indexer.
    """
    if not os.path.isfile(index_file):
        raise FileNotFoundError(
            f'Index file "{index_file}" not found – have you run `index_project`?'
        )

    with open(index_file, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_definition_code(
    file_path: str | os.PathLike, line: int, end_line: int
) -> str | None:
    """
    Read the source code for a definition directly from the file using the
    line and end_line information from the index. Returns ``None`` if the
    file cannot be read for any reason.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Convert from 1-based to 0-based indexing
        start_idx = line - 1
        end_idx = end_line

        if start_idx < 0 or start_idx >= len(lines) or end_idx > len(lines):
            print(f"[find_block] Invalid line range for {file_path}: {line}-{end_line}")
            return None

        code_lines = lines[start_idx:end_idx]
        return "".join(code_lines).rstrip()

    except Exception as exc:  # pragma: no cover  (best-effort – don't crash)
        print(f"[find_block] Failed to read {file_path}: {exc}")

    return None


def find_definitions(
    target: str,
    *,
    index_file: str | os.PathLike = USAGES_INDEX_FILE,
    include_code: bool = True,
) -> list[DefinitionRecord]:
    """
    Locate **classes, functions, or methods** whose *simple name* equals
    ``target`` **or** whose FQN ends with ``target`` (case-sensitive).

    Parameters
    ----------
    target:
        Symbol name to look for.  ``"MyClass"``, ``"my_package.utils.helper"``
        and similar strings are accepted.
    index_file:
        Path to the JSON file produced by :pyfunc:`indexer.index_project`.
    include_code:
        When *True*, an additional ``"code"`` key with the full source snippet
        will be included for every record.  This reads the source file directly
        using the line and end_line information from the index.

    Returns
    -------
    list[DefinitionRecord]
        Zero or more records, each describing one definition that matched the
        query.  If ``include_code`` is *True*, the ``code`` field is guaranteed
        to be present (but may be ``""`` if Jedi could not extract it).
    """
    index: list[IndexEntry] = _load_index(index_file)

    # simple heuristics: exact simple name match *or* trailing FQN match
    matches: list[IndexEntry] = [
        rec for rec in index if rec["name"] == target or rec["fqn"].endswith(target)
    ]

    if not matches:
        return []

    results: list[DefinitionRecord] = []
    seen: set[tuple[str, int, int]] = set()  # de-duplicate (file, line, column)

    for rec in matches:
        key = (rec["file"], rec["line"], rec["column"])
        if key in seen:
            continue
        seen.add(key)

        # ignore imports
        if rec["type"] in ("class", "function") and rec["line"] == rec["end_line"]:
            continue

        out: DefinitionRecord = rec.copy()

        if include_code:
            # Use end_line from an index if available, otherwise estimate it as line + 1
            end_line = rec.get("end_line", rec["line"] + 1)
            code = _read_definition_code(rec["file"], rec["line"], end_line)
            out["code"] = code or ""

        results.append(out)

    return results
