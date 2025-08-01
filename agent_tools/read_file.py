def read_file(
    path: str,
    start_line: int = 1,
    end_line: int | None = None,
    add_line_numbers: bool = False,
) -> str:
    """
    Read content from a file between specified line numbers.

    Args:
        path: Path to the file to read
        start_line: First line to read (1-based indexing, default: 1)
        end_line: Last line to read (inclusive). If None, reads until end of file
        add_line_numbers: If True, adds line numbers with a colon at the beginning of each line

    Returns:
        String containing the requested lines from the file
    """
    if not path:
        raise ValueError("Path cannot be empty")

    if start_line < 1:
        raise ValueError("start_line must be at least 1 (1-based indexing)")

    if end_line is not None and end_line < start_line:
        raise ValueError("end_line must be greater than or equal to start_line")

    with open(path, "r", encoding="utf-8") as file:
        lines: list[str] = file.readlines()

        # Handle empty file case
        if not lines:
            return ""

        if start_line > len(lines):
            raise ValueError("start_line exceeds file length")

        if end_line is None:
            end_line = len(lines)
        elif end_line > len(lines):
            end_line = len(lines)

        if add_line_numbers:
            result = ""
            for i, line in enumerate(lines[start_line - 1 : end_line]):
                line_number = start_line + i
                result += f"{line_number}: {line}"
            return result
        else:
            return "".join(lines[start_line - 1 : end_line])
