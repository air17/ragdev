from ripgrepy import Ripgrepy, RipGrepOut


def search_codebase(query: str, path: str = ".") -> str:
    """Search codebase for a given query pattern.

    Args:
        query: Pattern to search for in the codebase
        path: Directory path to search in. Defaults to a current directory.
        print_results: Whether to print results to stdout. Defaults to True.

    Returns:
        String containing search results with filenames and line numbers.
    """
    results: RipGrepOut = Ripgrepy(query, path).with_filename().line_number().run()

    return results.as_string
