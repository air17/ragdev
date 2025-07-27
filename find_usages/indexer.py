import os
import json
from typing import TypedDict, Optional
import jedi
from jedi.api.classes import Name

from config import USAGES_INDEX_FILE


class IndexEntry(TypedDict):
    """Type definition for a single index entry."""

    name: str  # simple name
    fqn: str  # fully qualified name
    module: str  # dotted module path
    file: str  # file path
    line: int  # line number
    end_line: int  # end line number
    column: int  # column number
    type: str  # type of the name


def is_test_directory(dir_name: str) -> bool:
    """Check if the directory is a test directory."""
    return dir_name.startswith("test") or dir_name.endswith("tests")


def is_test_file(file_name: str) -> bool:
    """Check if the file is a test file."""
    return file_name.startswith("test_") or file_name.endswith("_test.py")


def is_python_file(file_name: str) -> bool:
    """Check if the file is a Python file."""
    return file_name.endswith(".py")


def get_module_path(file_path: str, root_path: str) -> str:
    """Get a dotted module path from file path relative to root."""
    rel_path = os.path.relpath(file_path, root_path)
    return rel_path[:-3].replace(os.sep, ".")


def parse_file(
    file_path: str, project: jedi.Project
) -> Optional[list[jedi.api.classes.Name]]:
    """Parse a Python file using Jedi and return names."""
    try:
        script = jedi.Script(path=file_path, project=project)
        return script.get_names(all_scopes=True, definitions=True)
    except Exception as e:
        print(f"Failed to parse {file_path}: {e}")
        return None


def create_index_entry(
    name_obj: Name, module: str, file_path: str
) -> IndexEntry | None:
    """Create an index entry from a Jedi name object."""
    # Filter out builtins and imports
    valid_types = ("class", "function", "module", "instance", "param", "path")
    if name_obj.type not in valid_types:
        return None

    end_line: int | None = (
        name_obj.get_definition_end_position()[0]
        if name_obj.get_definition_end_position()
        else None
    )

    return IndexEntry(
        name=name_obj.name,
        fqn=f"{module}.{name_obj.name}",
        module=module,
        file=file_path,
        line=name_obj.line,
        end_line=end_line or name_obj.line,
        column=name_obj.column,
        type=name_obj.type,
    )


def write_index_to_file(index: list[IndexEntry], out_file: str) -> None:
    """Write the index to a JSON file."""
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    print(f"Index written to {out_file} ({len(index)} entries)")


def index_project(root_path: str, out_file: str = USAGES_INDEX_FILE) -> None:
    """
    Walk through all .py files under root_path, collect all definitions (classes, functions, variables)
    using Jedi, and write an index file as JSON.

    Note: Test files (prefixed with 'test_' or ending with '_test.py') and test directories
    (prefixed with 'test' or ending with 'tests') are excluded from indexing.
    """
    project = jedi.Project(path=root_path)
    index: list[IndexEntry] = []

    for dirpath, dirs, files in os.walk(root_path):
        # Skip test directories
        dirs[:] = [
            d for d in dirs if not is_test_directory(d) and not d.startswith(".")
        ]

        for fname in files:
            if not is_python_file(fname) or is_test_file(fname):
                continue

            full_path = os.path.join(dirpath, fname)
            module = get_module_path(full_path, root_path)

            names = parse_file(full_path, project)
            if names is None:
                continue

            for name in names:
                entry = create_index_entry(name, module, full_path)
                if entry is not None:
                    index.append(entry)

    write_index_to_file(index, out_file)
