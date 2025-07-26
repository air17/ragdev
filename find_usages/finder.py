import json
import os
from typing import TypedDict

import jedi

from config import USAGES_INDEX_FILE


class UsageRecord(TypedDict):
    """
    Structure returned by `find_usages`.
    """

    path: str
    line: int
    column: int
    fqn: str


def find_usages(
    root: str, target: str, index_file: str = USAGES_INDEX_FILE
) -> list[UsageRecord]:
    """
    Load index, resolve target to definitions, then use Jedi to find references.

    Args:
        root: Root directory of the project
        index_file: Path to the index file created by index_project
        target: Name or fully qualified name to find usages of

    Returns:
        List of dictionaries containing usage information:
        [
            {
                'path': str,  # Path to the file containing the usage
                'line': int,  # Line number
                'column': int,  # Column number
                'fqn': str  # Fully qualified name of the target
            },
            ...
        ]
    """
    if not os.path.isfile(index_file):
        raise FileNotFoundError(
            f'Index file "{index_file}" not found. Run index_project first.'
        )

    with open(index_file, "r", encoding="utf-8") as f:
        index = json.load(f)

    # match definitions where simple name equals target or fqn endswith target
    defs = [
        rec for rec in index if rec["name"] == target or rec["fqn"].endswith(target)
    ]
    if not defs:
        return []

    project = jedi.Project(path=root)
    seen = set()
    results = []

    for rec in defs:
        file = rec["file"]
        line = rec["line"]
        column = rec["column"]
        try:
            script = jedi.Script(path=file, project=project)
            refs = script.get_references(
                line=line, column=column, include_builtins=False
            )
        except Exception as e:
            print(f"Jedi failed on {file}:{line}:{column}: {e}")
            continue
        for ref in refs:
            key = (ref.module_path, ref.line, ref.column)
            if key in seen:
                continue
            seen.add(key)
            path = ref.module_path or file
            results.append(
                {
                    "path": str(path),
                    "line": ref.line,
                    "column": ref.column,
                    "fqn": rec["fqn"],
                }
            )

    return results
