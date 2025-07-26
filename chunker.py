import ast
from typing import TypedDict, Literal


class ChunkDict(TypedDict):
    start: int
    end: int
    type: Literal["FunctionDef", "ClassDef", "Block"]


def chunk_file(
    path: str, max_lines: int = 30, max_func_lines: int = 50
) -> list[ChunkDict]:
    """
    Parse a Python file and split it into chunks.

    - Top-level FunctionDef and ClassDef each become their own chunks, regardless of size.
    - Any FunctionDef longer than `max_func_lines` is split by its body into sub-chunks of at most `max_func_lines` lines.
    - Other top-level statements are grouped into `Block` chunks of at most `max_lines` lines.

    Returns:
        List of dicts representing chunks, each with:
        - `start`: Starting line number of the chunk
        - `end`: Ending line number of the chunk
        - `type`: Type of the chunk, either "FunctionDef", "ClassDef", or "Block".
    """
    with open(path, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    def chunk_nodes(nodes, max_window, max_func_window) -> list[ChunkDict]:
        """Recursively chunk AST nodes into blocks and function definitions.
        Args:
            nodes (list): List of AST nodes to chunk.
            max_window (int): Maximum number of lines for a block.
            max_func_window (int): Maximum number of lines for a function body chunk.
        Returns:
            list: List of dictionaries representing chunks with start, end, and type.
        """
        chunks = []
        current = []

        def flush_block():
            if current:
                start = current[0].lineno
                end = current[-1].end_lineno
                chunks.append({"start": start, "end": end, "type": "Block"})
                current.clear()

        for node in nodes:
            # Always isolate FunctionDef and ClassDef
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                # Flush any pending non-block nodes
                flush_block()

                # Handle classes: single chunk
                if isinstance(node, ast.ClassDef):
                    chunks.append(
                        {
                            "start": node.lineno,
                            "end": node.end_lineno,
                            "type": "ClassDef",
                        }
                    )
                    continue

                # Handle functions
                length = node.end_lineno - node.lineno + 1
                # If small enough, single chunk
                if length <= max_func_window:
                    chunks.append(
                        {
                            "start": node.lineno,
                            "end": node.end_lineno,
                            "type": "FunctionDef",
                        }
                    )
                else:
                    # Split function into approximately two halves
                    body = node.body
                    if not body:
                        # Edge case: function has no body
                        chunks.append(
                            {
                                "start": node.lineno,
                                "end": node.end_lineno,
                                "type": "FunctionDef",
                            }
                        )
                        continue

                    # Find the midpoint node index
                    midpoint_idx = len(body) // 2

                    # First half: from function start to the end of the midpoint node
                    chunks.append(
                        {
                            "start": node.lineno,
                            "end": body[midpoint_idx].end_lineno,
                            "type": "FunctionDef",
                        }
                    )

                    # Second half: from the start of the next node to the end of the function
                    if midpoint_idx + 1 < len(body):
                        chunks.append(
                            {
                                "start": body[midpoint_idx + 1].lineno,
                                "end": node.end_lineno,
                                "type": "FunctionDef",
                            }
                        )
                continue

            # Other nodes: group into blocks
            current.append(node)
            # If block exceeds max_window, flush all but last
            span = current[-1].end_lineno - current[0].lineno + 1
            if span > max_window:
                # Remove last, flush, then start new with last
                last = current.pop()
                flush_block()
                current.append(last)

        # Final flush for remaining non-block nodes
        flush_block()
        return chunks

    return chunk_nodes(tree.body, max_lines, max_func_lines)
