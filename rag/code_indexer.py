import os

from config import DEFAULT_COLLECTION_NAME
from .chunker import chunk_file
from .embeddings import EmbeddingManager


def process_directory(
    manager: EmbeddingManager,
    directory: str = ".",
    file_extensions: tuple[str] = (".py",),
    max_lines: int = 30,
    max_func_lines: int = 50,
) -> None:
    """
    Process all files in a directory and its subdirectories, chunk them, and add them to the vector database.

    Args:
        manager (EmbeddingManager): Instance of the embedding manager to handle vector DB operations.
        directory (str): Directory path to process, defaults to current directory.
        file_extensions (tuple[str]): List of file extensions to process.
        max_lines (int): Maximum number of lines for a regular chunk.
        max_func_lines (int): Maximum number of lines for a function chunk.
    """
    # Get absolute path if relative path is provided
    abs_directory = os.path.abspath(directory)
    print(f"Processing files in {abs_directory}")

    for root, dirs, files in os.walk(abs_directory):
        for filename in files:
            file_path = os.path.join(root, filename)

            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in file_extensions:
                continue

            rel_path = os.path.relpath(file_path, abs_directory)
            print(f"Processing file: {rel_path}")
            try:
                # Generate chunks for the file
                chunks = chunk_file(file_path, max_lines, max_func_lines)

                # Process each chunk
                for chunk in chunks:
                    start_line = chunk["start"]
                    end_line = chunk["end"]

                    # Read the specific chunk content
                    with open(file_path, "r", encoding="utf-8") as f:
                        all_lines = f.readlines()
                        # Convert to 0-based indexing for list slicing
                        chunk_content = "".join(all_lines[start_line - 1 : end_line])

                    # Add chunk to vector database
                    print(
                        f"Adding chunk {start_line}-{end_line} ({chunk['type']}) to vector DB"
                    )
                    manager.add_to_vector(chunk_content, rel_path, start_line, end_line)

            except Exception as e:
                print(f"Error processing {rel_path}: {str(e)}")


def index(directory: str = ".", collection_name: str = DEFAULT_COLLECTION_NAME) -> None:
    """
    Main function to process files and add them to the vector database.

    Args:
        directory (str): Directory path to process, defaults to current directory.
    """
    manager: EmbeddingManager = EmbeddingManager(collection_name=collection_name)

    # Create collection if it doesn't exist
    if not manager.create_collection_if_not_exists():
        print(f"Cleaning up existing collection: {manager.collection_name}")
        manager.drop_collection()
        manager.create_collection_if_not_exists()

    # Process files
    process_directory(manager, directory=directory)
