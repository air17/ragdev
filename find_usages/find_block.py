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
from typing import Any, TypedDict

import jedi
from jedi.api.classes import Name

from config import USAGES_INDEX_FILE


class DefinitionRecord(TypedDict, total=False):
    """
    A single definition entry returned by ``find_definitions``.
    The layout mirrors the structure written by the indexer with the addition
    of an optional ``code`` field containing the definition's source code.
    """

    # mandatory fields – they always exist in the index file
    name: str
    fqn: str
    module: str
    file: str
    line: int
    column: int

    # optional – filled only when `include_code=True`
    code: str


def _load_index(index_file: str | os.PathLike) -> list[dict[str, Any]]:
    """
    Load and return the raw JSON content produced by the indexer.
    """
    if not os.path.isfile(index_file):
        raise FileNotFoundError(
            f'Index file "{index_file}" not found – have you run `index_project`?'
        )

    with open(index_file, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _extract_definition_code(
    file_path: str | os.PathLike, line: int, column: int
) -> str | None:
    """
    Use Jedi to obtain the exact source code for a definition located at the
    given line/column.  Returns ``None`` if Jedi fails for any reason.
    """
    try:
        script = jedi.Script(path=str(file_path))
        # Using `infer` would also work here, but `get_names` is cheap and allows
        # direct coordinate matching which is immune to ambiguities.
        name_obj: Name
        for name_obj in script.get_names(all_scopes=True, definitions=True):
            if name_obj.line == line:
                # unwrap the Name -> parso leaf -> parent (= funcdef / classdef)
                return name_obj._name.tree_name.parent.get_code().rstrip()

    except Exception as exc:  # pragma: no cover  (best-effort – don't crash)
        print(f"[find_block] Jedi failed while parsing {file_path}: {exc}")

    return None


def find_definitions(
    target: str,
    *,
    index_file: str | os.PathLike = USAGES_INDEX_FILE,
    include_code: bool = False,
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
        will be included for every record.  This requires parsing each source
        file with Jedi and is therefore a bit slower.

    Returns
    -------
    list[DefinitionRecord]
        Zero or more records, each describing one definition that matched the
        query.  If ``include_code`` is *True*, the ``code`` field is guaranteed
        to be present (but may be ``""`` if Jedi could not extract it).
    """
    index = _load_index(index_file)

    # simple heuristics: exact simple name match *or* trailing FQN match
    matches = [
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

        out: DefinitionRecord = {
            "name": rec["name"],
            "fqn": rec["fqn"],
            "module": rec["module"],
            "file": rec["file"],
            "line": rec["line"],
            "column": rec["column"],
        }

        if include_code:
            code = _extract_definition_code(rec["file"], rec["line"], rec["column"])
            out["code"] = code or ""

        results.append(out)

    return results
