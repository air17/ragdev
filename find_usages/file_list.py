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
