from ripgrepy import Ripgrepy


def search_codebase(query: str, path: str = ".", root_path: str | None = None) -> str:
    """Search codebase for a given query pattern.

    Args:
        query: Pattern to search for in the codebase
        path: Directory path to search in. Defaults to a current directory.
        root_path: Base directory to remove from file paths in results. If None, does not modify paths.

    Returns:
        String containing search results with filenames and line numbers.
        Excludes files in 'tests' directories, files starting with 'test', and hidden files.
    """
    max_results: int = 50
    max_line_length: int = 300

    results: str = (
        Ripgrepy(query, path)
        .with_filename()
        .line_number()
        .trim()
        .smart_case()
        .glob("!**/tests/**")  # skip tests/ subtrees
        .glob("!**/test*.py")  # skip individual test_*.py files
        .glob("!**/.*")  # skip hidden files/dirs
        .glob("!**/__*__/**")  # skip any __name__/ directory
        .run()
        .as_string
    )
    lines: list[str] = results.splitlines()
    # limit number of results
    if len(lines) > max_results:
        lines = lines[:max_results] + [
            f"...{len(lines) - max_results} results truncated..."
        ]
    # limit line length
    lines = [
        line[:max_line_length] + "... (line truncated)"
        if len(line) > max_line_length
        else line
        for line in lines
    ]
    # make paths relative to root_path
    if root_path:
        lines = [line.replace(root_path + "/", "") for line in lines]
    return "\n".join(lines)
