import os


def create_file_tree(directory: str = ".") -> str:
    """
    Build a lightweight, human-readable tree of the project that lists only
    files with selected extensions while omitting:
      • hidden directories (starting with “.”)
      • test directories (starting with “test”)

    Parameters
    ----------
    directory : str, default="."
        Root directory to start the walk from.

    Returns
    -------
    str
        A newline-separated tree where each directory appears once followed by
        its relevant files, indented with four spaces per nesting level.
    """
    allowed_ext: tuple[str, ...] = (
        ".py",
        ".html",
        ".htm",
        ".yaml",
        ".yml",
        ".md",
        ".txt",
    )
    lines: list[str] = []

    # Collect lines first for faster string building
    for root, dirs, files in os.walk(directory):
        # In-place pruning of directories so os.walk() never descends into them
        dirs[:] = [d for d in dirs if not (d.startswith("test") or d.startswith("."))]

        relevant_files = [f for f in files if f.endswith(allowed_ext)]
        if not relevant_files:
            continue

        rel_root = os.path.relpath(root, directory)
        level = 0 if rel_root == "." else rel_root.count(os.sep)
        indent = " " * 4 * level

        lines.append(f"{indent}{os.path.basename(root) if level else rel_root}")
        indentation_spaces = " " * 4 * (level + 1)
        lines.extend(
            f"{indentation_spaces}{file_name}" for file_name in sorted(relevant_files)
        )

    return "\n".join(lines)
