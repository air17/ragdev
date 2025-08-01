import glob
import os


def ls(path: str = ".") -> str:
    """
    List the entries in the given directory and return them as a newline-separated string.

    :param path: Directory path to list
    :return: String with one entry per line, or an error message
    """
    try:
        entries = sorted(os.listdir(path))
        return "\n".join(entries)
    except FileNotFoundError:
        return f"ls: cannot access '{path}': No such file or directory"
    except NotADirectoryError:
        return f"ls: cannot access '{path}': Not a directory"
    except PermissionError:
        return f"ls: cannot open directory '{path}': Permission denied"
    except Exception as e:
        return f"ls: {e}"


def search_files_recursive(
    pattern: str, directory: str = ".", root_dir: str | None = None
) -> str:
    """
    Search for files recursively using glob patterns and return formatted results.

    Args:
        pattern (str): The glob pattern to search for
        directory (str): The directory to search in (default: current directory)
        root_dir (str, optional): Base directory for computing relative paths. If None, uses directory as base.

    Returns:
        str: Formatted string with search results for LLM consumption
    """
    # Join directory and pattern with ** for recursive search
    search_path: str = os.path.join(directory, "**", pattern)

    # Use glob with recursive=True
    matching_files: list[str] = glob.glob(search_path, recursive=True)

    # Format results for LLM understanding
    if not matching_files:
        return f"No files found matching pattern '{pattern}' in directory '{directory}'"

    if root_dir is None:
        root_dir = directory

    result: str = f"Found {len(matching_files)} file(s) matching pattern '{pattern}' in directory '{directory}':\n"
    for i, file_path in enumerate(matching_files, 1):
        # Get relative path for cleaner output
        rel_path: str = os.path.relpath(file_path, root_dir)
        try:
            file_size: int = (
                os.path.getsize(file_path) if os.path.exists(file_path) else 0
            )
        except (OSError, IOError):
            file_size = 0
        result += f"{i}. {rel_path} ({file_size} bytes)\n"

    return result.strip()
