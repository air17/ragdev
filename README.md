# RAG Development Project

This project implements a Retrieval-Augmented Generation (RAG) system. The core RAG capabilities are now mostly based on powerful `grep` search for robust and exact code retrieval. Previously, it relied heavily on Milvus for vector storage and Google's Gemini for embeddings, which are now considered optional/obsolete features.

## Features

- **Grep-based Code Search**: Core RAG capability relies on grep for accurate and fast exact match code retrieval
- **Telegram Bot Interface**: Interact with the system directly via Telegram
- **Code Symbol Usage**: Functions to find symbol usages in Python code
- **Intelligent Code Chunking** (Optional): Parses Python files and splits them into meaningful chunks based on function definitions, class definitions, and code blocks
- **Vector Embeddings** (Optional/Obsolete): Generates embeddings for code chunks using Google's Gemini API and stores them in Milvus

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

Edit the `.env` file and replace the placeholder values with your actual credentials.

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

## Configuration Management

The project uses a centralized configuration system:

- Environment variables are loaded from the `.env` file if it exists
- If a variable is not found in the `.env` file, it falls back to system environment variables
- Default values are provided as a last resort (not recommended for production)

## Project Structure

- `agent.py`: Agent functionality utilizing grep search for RAG
- `main.py`: Convenience helpers
- `telegram_bot/`: Code for the Telegram Bot interface
- `find_usages/`: Package for finding symbol usages in Python code
- `rag/`: Contains optional/obsolete chunking and embedding code (`chunker.py`, `embeddings.py`, `code_indexer.py`)
- `config.py`: Centralizes configuration management
- `tests/`: Project-level tests
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

---

## Obsolete / Optional Features (Milvus & Embeddings)

*The following functionality was part of the original vector-based RAG strategy but is now largely superseded by grep-based search.*

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
