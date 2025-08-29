# RAG Development Project

This project implements a Retrieval-Augmented Generation (RAG) system using Milvus for vector storage and Google's Gemini for embeddings. It's designed to process code files, chunk them intelligently, generate embeddings, and store them in a vector database for efficient retrieval.

## Features

- **Intelligent Code Chunking**: Parses Python files and splits them into meaningful chunks based on function definitions, class definitions, and code blocks
- **Vector Embeddings**: Generates embeddings for code chunks using Google's Gemini API
- **Vector Storage**: Stores embeddings and metadata in Milvus vector database
- **Similarity Search**: Retrieves the most relevant code chunks for a given query
- **Code Snippet Retrieval**: Returns actual code snippets along with search results for better context

## Installation

1. Clone the repository:

```bash
git clone https://github.com/air17/ragdev.git
cd ragdev
```

2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Set up pre-commit hooks (recommended for development):

```bash
pip install pre-commit
pre-commit install
```

This will ensure code quality checks run automatically before each commit and tests run before each push.

## Environment Setup

This project uses environment variables to manage configuration and secrets. Follow these steps to set up your environment:

### 1. Create a .env File

Copy the example environment file to create your own:

```bash
cp .env.example .env
```

### 2. Configure Your Environment Variables

Edit the `.env` file and replace the placeholder values with your actual credentials:

```
# Milvus configuration
MILVUS_ENDPOINT=https://your-milvus-endpoint.example.com
MILVUS_TOKEN=your-milvus-token-here

# Gemini configuration
GEMINI_API_KEY=your-gemini-api-key-here

# Default collection name
DEFAULT_COLLECTION_NAME=code_chunks
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| MILVUS_ENDPOINT | URL endpoint for your Milvus instance | Yes |
| MILVUS_TOKEN | Authentication token for Milvus | Yes |
| GEMINI_API_KEY | API key for Google's Gemini AI service | Yes |
| DEFAULT_COLLECTION_NAME | Default name for the Milvus collection | No (defaults to "code_chunks") |

## Usage

### Running the Telegram Bot

For development and testing, you can run the bot directly:

```bash
python -c "import asyncio; from telegram_bot.main import setup_production_bot; asyncio.run(setup_production_bot())"
```


Alternatively, you can use `nohup` to ensure the process continues even after closing the terminal:

```bash
# Start with nohup (more robust for production)
nohup python -c "import asyncio; from telegram_bot.main import setup_production_bot; asyncio.run(setup_production_bot())" > bot.log 2>&1 &

# The process will continue running even after terminal disconnect
```

### Managing Embeddings

#### Initial Setup - Generate Embeddings
To generate embeddings for your project for the first time:

```python
from main import index_all

# Generate embeddings for the current directory
index_all()

# Or for a specific directory
index_all(directory="/path/to/your/project")
```

#### Regenerate Embeddings (Clear and Rebuild)
To completely regenerate embeddings (useful when you want to start fresh or after major code changes), you can manually clear and rebuild embeddings:

```python
from main import index_all

index_all(resume=False)
```

**Note**: Regenerating embeddings will:
1. Delete the existing Milvus collection and all stored embeddings
2. Create a fresh collection
3. Process and index all files from scratch

This is different from `index_all()` which resumes from previous progress by default.

### Quick start with `main.py`

```python
from main import index_all, search_code, search_code_with_snippets

# 1) build both indices (vector + symbol usages)
index_all()  # or index_all(directory="/path/to/your/project")

# 2) semantic code search
results = search_code("How do I parse Python files?", top_k=5)
for res in results:
    print(res)

# 3) semantic code search with snippets
results_with_snippets = search_code_with_snippets("How do I parse Python files?", top_k=5)
for res in results_with_snippets:
    print(f"File: {res['entity']['filename']}, Lines: {res['entity']['start_line']}-{res['entity']['end_line']}")
    print(f"Snippet:\n{res['snippet']}")
    print("-" * 80)
```

### Indexing Code Files

To index Python files in a directory:

```python
from main import index_all

# Index files in the current directory (builds both indices)
index_all()

# Index files in a specific directory
index_all(directory="/path/to/your/code")
```

### Retrieving Similar Code

To retrieve code chunks similar to a query:

```python
from main import search_code

hits = search_code("How do I parse Python files?", top_k=5)
for hit in hits:
    print(f"File: {hit['filename']}, Lines: {hit['start_line']}-{hit['end_line']}, score: {hit['score']}")
```

To retrieve code chunks with the actual code snippets:

```python
from main import search_code_with_snippets

hits_with_snippets = search_code_with_snippets("How do I parse Python files?", top_k=5)
for hit in hits_with_snippets:
    print(f"File: {hit['entity']['filename']}, Lines: {hit['entity']['start_line']}-{hit['entity']['end_line']}")
    print(f"Score: {hit['distance']}")
    print("Code snippet:")
    print(hit['snippet'])
    print("-" * 50)
```

## Configuration Management

The project uses a centralized configuration system:

- Environment variables are loaded from the `.env` file if it exists
- If a variable is not found in the `.env` file, it falls back to system environment variables
- Default values are provided as a last resort (not recommended for production)

## Project Structure

- `main.py`: Convenience helpers – build indices, semantic search & find usages
- `rag/chunker.py`: Handles parsing and chunking of Python files
- `rag/embeddings.py`: Manages vector embeddings and Milvus operations
- `rag/code_indexer.py`: Handles the indexing of code files
- `rag/snippet_reader.py`: Extracts code snippets from files based on search results
- `config.py`: Centralizes configuration management
- `find_usages/`: Package for finding symbol usages in Python code
- `tests/`: Project-level tests
- `rag/tests/`: Tests for the RAG module
- `find_usages/tests/`: Tests for the find_usages module
- `requirements.txt`: Lists project dependencies

## Testing

This project uses pytest for testing. Tests are organized in a modular structure:

- Project-level tests in the `tests/` directory
- Module-specific tests in `rag/tests/` and `find_usages/tests/` directories

### Running Tests

To run all tests:

```bash
pytest
```

To run tests for a specific module:

```bash
pytest rag/tests/
pytest agent_tools/tests/
```

## Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality. The following hooks are configured:

### Standard Hooks
- `end-of-file-fixer`: Ensures files end with a newline
- `trailing-whitespace`: Removes trailing whitespace
- `detect-private-key`: Prevents committing private keys
- `requirements-txt-fixer`: Sorts requirements.txt
- `check-docstring-first`: Ensures docstrings come before code

### Code Quality Hooks
- `ruff`: Python linter with auto-fix capability
- `ruff-format`: Python code formatter

### Testing Hooks
- `pytest`: Runs all tests on push (not on commit)

### Installing Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

This will ensure code quality checks run automatically before each commit, and tests run before each push.

## Security Notes

- Never commit your `.env` file to version control
- The `.env` file is already included in `.gitignore`
- For production deployments, use system environment variables or a secure secrets management service
