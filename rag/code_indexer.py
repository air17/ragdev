import os

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
    Process all files in a directory, chunk them, and add them to the vector database.

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

    for filename in os.listdir(abs_directory):
        file_path = os.path.join(abs_directory, filename)

        # Skip directories and non-matching extensions
        if os.path.isdir(file_path):
            continue

        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in file_extensions:
            continue

        print(f"Processing file: {filename}")
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
                manager.add_to_vector(chunk_content, filename, start_line, end_line)

        except Exception as e:
            print(f"Error processing {filename}: {str(e)}")


def index(directory: str = ".") -> None:
    """
    Main function to process files and add them to the vector database.

    Args:
        directory (str): Directory path to process, defaults to current directory.
    """
    manager: EmbeddingManager = EmbeddingManager(collection_name="ragdev")

    # Create collection if it doesn't exist
    if not manager.create_collection_if_not_exists():
        print(f"Cleaning up existing collection: {manager.collection_name}")
        manager.drop_collection()
        manager.create_collection_if_not_exists()

    # Process files
    process_directory(manager, directory=directory)
