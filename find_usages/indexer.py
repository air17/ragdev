import os
import json
import jedi


def index_project(root_path: str, out_file: str = "usages_index.json") -> None:
    """
    Walk through all .py files under root_path, collect all definitions (classes, functions, variables)
    using Jedi, and write an index file as JSON.
    Each record: {
      'name': name,          # simple name
      'fqn': module_path + '.' + name,
      'module': module_path, # dotted module path
      'file': file_path,
      'line': line,
      'column': column
    }

    Note: Test files (prefixed with 'test_' or ending with '_test.py') and test directories
    (prefixed with 'test' or ending with 'tests') are excluded from indexing.
    """
    project = jedi.Project(path=root_path)
    index = []
    for dirpath, dirs, files in os.walk(root_path):
        # Skip test directories
        dirs[:] = [
            d for d in dirs if not d.startswith("test") and not d.endswith("tests")
        ]

        for fname in files:
            if not fname.endswith(".py"):
                continue

            # Skip test files
            if fname.startswith("test_") or fname.endswith("_test.py"):
                continue

            full_path = os.path.join(dirpath, fname)
            # module path relative to root
            rel = os.path.relpath(full_path, root_path)
            module = rel[:-3].replace(os.sep, ".")
            # use Jedi to parse
            try:
                script = jedi.Script(path=full_path, project=project)
                names = script.get_names(all_scopes=True, definitions=True)
            except Exception as e:
                print(f"Failed to parse {full_path}: {e}")
                continue
            for name in names:
                # filter out builtins and imports
                if name.type in (
                    "class",
                    "function",
                    "module",
                    "instance",
                    "param",
                    "path",
                ):
                    index.append(
                        {
                            "name": name.name,
                            "fqn": f"{module}.{name.name}",
                            "module": module,
                            "file": full_path,
                            "line": name.line,
                            "column": name.column,
                        }
                    )
    # write index
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    print(f"Index written to {out_file} ({len(index)} entries)")
