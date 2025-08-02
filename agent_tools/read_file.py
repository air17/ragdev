import ast
import re

IMPORT_RE = re.compile(r"^\s*(?:import|from)\b")
TRIPLE_QUOTE_RE = re.compile(r'([\'"]{3})')


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


def summarize_chunk(code_lines: str) -> str:
    """
    Mock LLM function to generate a summary of the given text.
    This is a placeholder that should be replaced with actual LLM integration.

    Args:
        code_lines: Code lines to summarize

    Returns:
        A summary of the code lines
    """
    lines_limit: int = (
        4000  # 64k context * 4 symbols per token / 60 symbols per line = 4266
    )

    lines: list[str] = code_lines.splitlines()
    # filter out empty lines
    lines = [line for line in lines if line.strip()]
    # limit code lines
    code_lines = "\n".join(lines[:lines_limit])
    return f"First line: {lines[0]}\n-----\nLast line: {lines[-1]}"


def extract_top_level_imports(path: str) -> tuple[str, int]:
    """
    Extracts top-level import statements from a Python file, sorts them by line
    number, and retrieves the corresponding lines along with the line number of
    the last import statement.

    :param path: The file path to a Python script from which imports will be extracted.
    :type path: str
    :return: A tuple containing the extracted import statements
             (as a string with line numbers) and the line number directly
             following the last import statement.
    """
    # Parse the AST
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    # Pick only top-level import nodes
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if not imports:
        return "", 0

    # Sort and extract last line
    imports.sort(key=lambda node: node.lineno)
    last_import = imports[-1]
    last: int = getattr(last_import, "end_lineno", last_import.lineno) + 1

    return read_file(path, 1, last, add_line_numbers=True), last


def read_file_with_context(
    path: str,
    start_line: int = 1,
    end_line: int | None = None,
) -> str:
    """
    Read content from a file with additional context including imports and summaries.

    This function:
    1. Adds all import statements from the file (if not already in the start-end range).
    2. For the lines *before* start_line (between the end of imports and start_line):
       - If there are fewer than 10 lines, it inlines them.
       - Otherwise it generates a summary.
    3. Returns the requested content (start_line to end_line).
    4. For the lines *after* end_line (to the end of file):
       - If there are 10 or fewer lines, it inlines them.
       - Otherwise it generates a summary.

    Args:
        path: Path to the file to read.
        start_line: First line to read (1-based indexing, default: 1).
        end_line: Last line to read (inclusive). If None, reads until end of file.

    Returns:
        String containing imports, optional inlined context or summaries, and the requested content.
    """
    if not path:
        raise ValueError("Path cannot be empty")
    if start_line < 1:
        raise ValueError("start_line must be at least 1 (1-based indexing)")
    if end_line is not None and end_line < start_line:
        raise ValueError("end_line must be >= start_line")

    # Read entire file once
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total_lines = len(lines)
    if all(not line.strip() for line in lines):
        return "Empty file"

    # Normalize end_line
    end_line = total_lines if end_line is None or end_line > total_lines else end_line

    # Extract import lines
    import_lines, last_import_line = extract_top_level_imports(path)

    parts: list[str] = []

    # 1) Prepend imports if they lie entirely outside [start_line, end_line]
    if import_lines and not (start_line <= last_import_line <= end_line):
        parts.append("# Imports from file:")
        parts.append(import_lines)
        parts.append("")
        if start_line <= last_import_line:
            start_line = last_import_line + 1
            if end_line <= start_line:
                return "".join(parts)

    # Helper to format a slice of lines
    def format_slice(start: int, end: int, numbered: bool) -> str:
        chunk = lines[start - 1 : end]
        if numbered:
            return "".join(
                f"{i + 1}: {line}" for i, line in enumerate(chunk, start=start - 1)
            )
        else:
            return "".join(chunk)

    def add_lines_summary(start: int, end: int) -> None:
        count = end - start + 1
        if count <= 10:
            snippet = format_slice(start, end, True)
            parts.append(snippet)
        else:
            content = format_slice(start, end, False)
            summary: str = summarize_chunk(content)
            parts.append(f"Summary of lines {start}-{end}:")
            parts.append(f"{summary}")

    # 2) Context *before* start_line
    before_start = last_import_line + 1
    before_end = start_line - 1
    if before_start <= before_end:
        add_lines_summary(before_start, before_end)
        parts.append("...")

    # 3) Main requested content
    main = format_slice(start_line, end_line, numbered=True)
    parts.append(main)

    # 4) Context *after* end_line
    if end_line < total_lines:
        after_start = end_line + 1
        after_end = total_lines
        parts.append("...")
        add_lines_summary(after_start, after_end)
    return "\n".join(parts)
