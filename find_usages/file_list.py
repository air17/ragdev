import os


def create_file_tree(directory: str = ".", depth: int = 5) -> str:
    """
    Build a lightweight, human-readable tree of the project that lists only
    files with selected extensions while omitting:
      • hidden directories (starting with “.”)
      • test directories (starting with “test”)

    Parameters
    ----------
    directory : str, default="."
        Root directory to start the walk from.
    depth : int, default=5
        Maximum depth of the tree.

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

    # Normalize the root name for printing
    root_name: str = os.path.basename(os.path.abspath(directory)) or directory

    for root, dirs, files in os.walk(directory, topdown=True):
        # Compute nesting level properly:
        #   "" or "."  => 0
        #   "sub"      => 1
        #   "sub/a"    => 2, etc.
        rel_root = os.path.relpath(root, directory)
        if rel_root in (".", ""):
            level = 0
            display_name = root_name
        else:
            level = len(rel_root.split(os.sep))
            display_name = os.path.basename(root)

        # Skip entirely if this directory is deeper than allowed
        if level > depth:
            # remove all children so os.walk won't descend further
            dirs.clear()
            continue

        # Prune test/hidden dirs and those that would exceed depth
        dirs[:] = [
            d
            for d in dirs
            if not (d.startswith("test") or d.startswith(".")) and level + 1 <= depth
        ]

        # Collect only the files we care about
        relevant = sorted(f for f in files if f.endswith(allowed_ext))
        if not relevant:
            continue

        indent = " " * 4 * level
        lines.append(f"{indent}{display_name}")
        file_indent = " " * 4 * (level + 1)
        for fname in relevant:
            lines.append(f"{file_indent}{fname}")

    return "\n".join(lines)
