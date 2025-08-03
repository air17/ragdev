from ripgrepy import Ripgrepy


def search_codebase(query: str, path: str = ".") -> str:
    """Search codebase for a given query pattern.

    Args:
        query: Pattern to search for in the codebase
        path: Directory path to search in. Defaults to a current directory.
        print_results: Whether to print results to stdout. Defaults to True.

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
        .glob("!**/tests/**")  # skip tests/ subtrees
        .glob("!**/test*.py")  # skip individual test_*.py files
        .glob("!**/.*")  # skip hidden files/dirs
        .glob("!**/__*__/**")  # skip any __name__/ directory
        .run()
        .as_string
    )
    lines: list[str] = results.splitlines()
    if len(lines) > max_results:
        lines = lines[:max_results] + [
            f"... {len(lines) - max_results} results truncated ..."
        ]
    lines = [
        line[:max_line_length] + "... (line truncated)"
        if len(line) > max_line_length
        else line
        for line in lines
    ]
    return "\n".join(lines)
