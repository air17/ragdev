import ast
import warnings
from typing import TypedDict, Literal


class ChunkDict(TypedDict):
    start: int
    end: int
    type: Literal["FunctionDef", "ClassDef", "Method", "Block"]


def split_node_into_chunks(
    node: ast.stmt,
    node_type: Literal["FunctionDef", "ClassDef", "Method", "Block"],
    max_func_lines: int,
) -> list[ChunkDict]:
    """
    .. deprecated::
        This function is not used by ChatAgent and will be removed in a future version.

    Split a function or method node into appropriate chunks.

    Args:
        node: The AST node (FunctionDef or Method) to split
        node_type: Type of the node ("FunctionDef" or "Method")
        max_func_lines: Maximum number of lines per chunk

    Returns:
        List of chunk dictionaries
    """
    warnings.warn(
        "split_node_into_chunks is deprecated and not used by ChatAgent. "
        "It will be removed in a future version.",
        DeprecationWarning,
        stacklevel=2,
    )
    result = []
    length = node.end_lineno - node.lineno + 1

    # If small enough, return as single chunk
    if length <= max_func_lines:
        result.append(
            ChunkDict(
                start=node.lineno,
                end=node.end_lineno,
                type=node_type,
            )
        )
        return result

    # Split a node into approximately two halves
    body = node.body
    if not body:
        # Edge case: node has no body
        result.append(
            ChunkDict(
                start=node.lineno,
                end=node.end_lineno,
                type=node_type,
            )
        )
        return result

    # Find the midpoint node index
    midpoint_idx = len(body) // 2

    # First half: from node start to the end of the midpoint node
    result.append(
        ChunkDict(
            start=node.lineno,
            end=body[midpoint_idx].end_lineno,
            type=node_type,
        )
    )

    # Second half: from the start of the next node to the end of the function/method
    if midpoint_idx + 1 < len(body):
        result.append(
            ChunkDict(
                start=body[midpoint_idx + 1].lineno,
                end=node.end_lineno,
                type=node_type,
            )
        )

    return result


def chunk_file(
    path: str, max_lines: int = 40, max_func_lines: int = 70
) -> list[ChunkDict]:
    """
    .. deprecated::
        This function is not used by ChatAgent and will be removed in a future version.

    Parse a Python file and split it into chunks.

    - Top-level FunctionDef becomes its own chunk.
    - ClassDef is split: if the class is larger than max_func_lines, the class definition becomes one chunk and each method becomes a separate chunk. Otherwise, the whole class is added as a single chunk.
    - Any FunctionDef or method longer than `max_func_lines` is split by its body into sub-chunks of at most `max_func_lines` lines.
    - Other top-level statements are grouped into `Block` chunks of at most `max_lines` lines.
    - Import statements are excluded from chunks.

    Returns:
        List of dicts representing chunks, each with:
        - `start`: Starting line number of the chunk
        - `end`: Ending line number of the chunk
        - `type`: Type of the chunk, either "FunctionDef", "ClassDef", "Method", or "Block".
    """
    warnings.warn(
        "chunk_file is deprecated and not used by ChatAgent. "
        "It will be removed in a future version.",
        DeprecationWarning,
        stacklevel=2,
    )
    with open(path, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    nodes: list[ast.AST] = tree.body

    chunks = []
    current = []

    def flush_block():
        if current:
            start = current[0].lineno
            end = current[-1].end_lineno
            chunks.append(ChunkDict(start=start, end=end, type="Block"))
            current.clear()

    for node in nodes:
        # Skip import statements
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        # Always isolate FunctionDef and ClassDef
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            # Flush any pending non-block nodes
            flush_block()

            # Handle classes
            if isinstance(node, ast.ClassDef):
                class_length = node.end_lineno - node.lineno + 1

                # If class is small enough, add it as a single chunk
                if class_length <= max_func_lines:
                    chunks.append(
                        ChunkDict(
                            start=node.lineno,
                            end=node.end_lineno,
                            type="ClassDef",
                        )
                    )
                    continue

                # Class is too large, split it: class definition + separate methods
                # Add the class definition itself as a chunk (excluding methods)
                class_start = node.lineno
                class_end = node.end_lineno

                # First, extract methods from the class body
                methods = []
                non_methods = []
                for class_node in node.body:
                    if isinstance(class_node, ast.FunctionDef):
                        methods.append(class_node)
                    else:
                        non_methods.append(class_node)

                # If there are methods, adjust the class end line to exclude methods
                if methods and non_methods:
                    class_end = max(item.end_lineno for item in non_methods)
                elif methods and not non_methods:
                    # If class only contains methods, just include the class declaration line
                    class_end = class_start

                # Add the class definition as a chunk
                chunks.append(
                    ChunkDict(
                        start=class_start,
                        end=class_end,
                        type="ClassDef",
                    )
                )

                # Process each method separately
                for method in methods:
                    method_chunks = split_node_into_chunks(
                        method, "Method", max_func_lines
                    )
                    chunks.extend(method_chunks)
                continue

            # Handle functions
            function_chunks = split_node_into_chunks(
                node, "FunctionDef", max_func_lines
            )
            chunks.extend(function_chunks)
            continue

        # Other nodes: group into blocks
        current.append(node)
        # If block exceeds max_window, flush all but last
        span = current[-1].end_lineno - current[0].lineno + 1
        if span > max_lines:
            # Remove last, flush, then start new with last
            last = current.pop()
            flush_block()
            current.append(last)

    # Final flush for remaining non-block nodes
    flush_block()
    return chunks
