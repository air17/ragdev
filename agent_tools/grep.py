from ripgrepy import Ripgrepy, RipGrepOut


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
    results: RipGrepOut = (
        Ripgrepy(query, path)
        .with_filename()
        .line_number()
        .glob("!**/tests/**")  # skip tests/ subtrees
        .glob("!**/test*.py")  # skip individual test_*.py files
        .glob("!**/.*")  # skip hidden files/dirs
        .glob("!**/__*__/**")  # skip any __name__/ directory
        .run()
    )

    return results.as_string
