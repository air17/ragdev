import os
import json
from pathlib import Path

from config import DEFAULT_COLLECTION_NAME
from agent_tools.read_file import read_file
from .chunker import chunk_file
from .embeddings import EmbeddingManager

# Default list of directories to exclude from indexing
DEFAULT_DIR_EXCLUSIONS: tuple[str, ...] = (
    "test",  # Test directories
    ".",  # Hidden directories
    "migrations",  # Database migrations
    "__pycache__",  # Python bytecode
    "venv",  # Virtual environments
    "env",  # Virtual environments
    "node_modules",  # Node.js dependencies
)
# Special case exclusions (directory name and parent directory name pairs)
DEFAULT_DIR_WITHIN_PARENT_EXCLUSIONS: tuple[tuple[str, str]] = (
    ("jl_main_project", "jetlend_models"),  # Specific to this project
)
DEFAULT_FILE_EXTENSIONS: tuple[str, ...] = (".py",)
DEFAULT_BATCH_SIZE: int = 100


def process_directory(
    manager: EmbeddingManager,
    directory: str = ".",
    file_extensions: tuple[str] = DEFAULT_FILE_EXTENSIONS,
    max_lines: int = 30,
    max_func_lines: int = 50,
    resume: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dir_exclusions: tuple[str, ...] = DEFAULT_DIR_EXCLUSIONS,
    dir_within_parent_exclusions: tuple[
        tuple[str, str], ...
    ] = DEFAULT_DIR_WITHIN_PARENT_EXCLUSIONS,
) -> None:
    """
    Process all files in a directory and its subdirectories, chunk them, and add them to the vector database.
    Skips directories in the exclusion lists and files starting with 'test'. Tracks already processed files to support resuming.

    Args:
        manager (EmbeddingManager): Instance of the embedding manager to handle vector DB operations.
        directory (str): Directory path to process, defaults to the current directory.
        file_extensions (tuple[str]): List of file extensions to process.
        max_lines (int): Maximum number of lines for a regular chunk.
        max_func_lines (int): Maximum number of lines for a function chunk.
        resume (bool): Whether to resume from previous indexing state, defaults to True.
        batch_size (int): Number of chunks to process in each batch, defaults to 20.
        dir_exclusions (list[str]): List of directory names to exclude, defaults to DEFAULT_DIR_EXCLUSIONS.
        dir_within_parent_exclusions (list[tuple[str, str]]): List of (parent_dir, dir) pairs for special exclusions.
    """
    # Get an absolute path if a relative path is provided
    abs_directory = os.path.abspath(directory)
    print(f"Processing files in {abs_directory}")

    # Create a state file path for this specific directory and collection
    directory_hash = abs_directory.replace("/", "_").replace("\\", "_").replace(":", "")
    state_file_path = Path(
        f"./.indexer_state_{directory_hash}_{manager.collection_name}.json"
    )
    indexed_files: set[str] = set()

    # Load previously indexed files if resuming
    if resume and state_file_path.exists():
        try:
            with open(state_file_path, "r") as f:
                state_data = json.load(f)
                indexed_files = set(state_data.get("indexed_files", []))
                print(
                    f"Resuming indexing: {len(indexed_files)} files already processed"
                )
        except Exception as e:
            print(f"Error loading indexer state: {str(e)}. Starting from scratch.")

    try:
        for root, dirs, files in os.walk(abs_directory):
            # In-place pruning of directories so os.walk() never descends into them
            dirs[:] = [
                d
                for d in dirs
                if not (
                    # Check against regular exclusions (startswith or exact match)
                    any(d.startswith(exclude) for exclude in dir_exclusions)
                    or
                    # Check against special case exclusions (parent_dir, dir pairs)
                    any(
                        os.path.basename(root) == parent and d == child
                        for parent, child in dir_within_parent_exclusions
                    )
                )
            ]
            for filename in files:
                file_path = os.path.join(root, filename)

                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in file_extensions:
                    continue

                # Skip test files
                if filename.lower().startswith("test_") or "tests/" in filename.lower():
                    print(f"Skipping test file: {filename}")
                    continue

                rel_path = os.path.relpath(file_path, abs_directory)

                # Skip already indexed files
                if rel_path in indexed_files:
                    print(f"Skipping already indexed file: {rel_path}")
                    continue

                print(f"Processing file: {rel_path}")
                try:
                    # Generate chunks for the file
                    chunks = chunk_file(file_path, max_lines, max_func_lines)

                    # Prepare batch processing variables
                    batch_chunks: list[tuple[str, str, int, int]] = []

                    # Process each chunk
                    for chunk in chunks:
                        start_line = chunk.get("start")
                        end_line = chunk.get("end")
                        chunk_content: str = read_file(file_path, start_line, end_line)
                        batch_chunks.append(
                            (chunk_content, rel_path, start_line, end_line)
                        )

                        # Add batch to vector database when batch size is reached
                        if len(batch_chunks) >= batch_size:
                            print(
                                f"Adding batch of {len(batch_chunks)} chunks to vector DB"
                            )
                            manager.add_to_vector_in_batch(batch_chunks)
                            batch_chunks = []

                    # Add any remaining chunks in the last batch
                    if batch_chunks:
                        print(
                            f"Adding final batch of {len(batch_chunks)} chunks to vector DB"
                        )
                        manager.add_to_vector_in_batch(batch_chunks)

                    # Mark file as indexed
                    indexed_files.add(rel_path)

                    # Update state file after each file to handle interruptions
                    with open(state_file_path, "w") as f:
                        json.dump({"indexed_files": list(indexed_files)}, f)

                except Exception as e:
                    print(f"Error processing {rel_path}: {str(e)}")
    except KeyboardInterrupt:
        print("\nIndexing interrupted. Progress has been saved.")
    except Exception as e:
        print(f"Unexpected error during indexing: {str(e)}")
    finally:
        # Make sure the final state is saved
        with open(state_file_path, "w") as f:
            json.dump({"indexed_files": list(indexed_files)}, f)
        print(f"Indexed {len(indexed_files)} files. State saved to {state_file_path}")


def index(
    directory: str = ".",
    collection_name: str = DEFAULT_COLLECTION_NAME,
    resume: bool = True,
    dir_exclusions: tuple[str, ...] = DEFAULT_DIR_EXCLUSIONS,
    dir_within_parent_exclusions: tuple[
        tuple[str, str]
    ] = DEFAULT_DIR_WITHIN_PARENT_EXCLUSIONS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """
    Main function to process files and add them to the vector database.

    Args:
        directory (str): Directory path to process, defaults to the current directory.
        collection_name (str): Name of the collection to use in the vector database.
        resume (bool): Whether to resume from previous indexing state, defaults to True.
        dir_exclusions (tuple[str]): List of directory names to exclude.
        dir_within_parent_exclusions (tuple[tuple[str, str]]): List of parent-child directory name pairs to exclude.
        batch_size (int): Number of files to process in a single batch, defaults to 100.
    """
    manager: EmbeddingManager = EmbeddingManager(collection_name=collection_name)

    # Create a collection if it doesn't exist
    if not manager.create_collection_if_not_exists():
        if resume:
            print(
                f"Collection '{manager.collection_name}' already exists. Skipping creation."
            )
        else:
            print(f"Cleaning up existing collection: {manager.collection_name}")
            manager.drop_collection()
            manager.create_collection_if_not_exists()

    # Process files
    process_directory(
        manager,
        directory=directory,
        resume=resume,
        dir_exclusions=dir_exclusions,
        dir_within_parent_exclusions=dir_within_parent_exclusions,
        batch_size=batch_size,
    )
