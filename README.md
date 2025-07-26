# RAG Development Project

This project implements a Retrieval-Augmented Generation (RAG) system using Milvus for vector storage and Google's Gemini for embeddings. It's designed to process code files, chunk them intelligently, generate embeddings, and store them in a vector database for efficient retrieval.

## Features

- **Intelligent Code Chunking**: Parses Python files and splits them into meaningful chunks based on function definitions, class definitions, and code blocks
- **Vector Embeddings**: Generates embeddings for code chunks using Google's Gemini API
- **Vector Storage**: Stores embeddings and metadata in Milvus vector database
- **Similarity Search**: Retrieves the most relevant code chunks for a given query

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/ragdev.git
cd ragdev
```

2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Install additional dependencies:

```bash
pip install google-generativeai  # For Gemini API
```

4. Set up pre-commit hooks (recommended for development):

```bash
pip install pre-commit
pre-commit install
```

This will ensure code quality checks run automatically before each commit.

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

### Quick start with `main.py`

```python
from main import index_all, search_code, find_symbol_usages

# 1) build both indices (vector + symbol usages)
index_all()  # or index_all(directory="/path/to/your/project")

# 2) semantic code search
results = search_code("How do I parse Python files?", top_k=5)
for res in results:
    print(res)

# 3) find all references to a symbol
usages = find_symbol_usages(".", "YourClass")
for u in usages:
    print(u)
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

### Finding Symbol Usages

To find all usages of a symbol:

```python
from main import find_symbol_usages

# Assuming the index has been built already with index_all()
results = find_symbol_usages("path/to/your/project", "YourClass")

for r in results:
    print(f"Found in {r['path']} at line {r['line']}, column {r['column']}")
```

## Configuration Management

The project uses a centralized configuration system:

- Environment variables are loaded from the `.env` file if it exists
- If a variable is not found in the `.env` file, it falls back to system environment variables
- Default values are provided as a last resort (not recommended for production)

## Project Structure

- `main.py`: Convenience helpers – build indices, semantic search & find usages
- `chunker.py`: Handles parsing and chunking of Python files
- `embeddings.py`: Manages vector embeddings and Milvus operations
- `config.py`: Centralizes configuration management
- `find_usages/`: Package for finding symbol usages in Python code
- `requirements.txt`: Lists project dependencies

## Security Notes

- Never commit your `.env` file to version control
- The `.env` file is already included in `.gitignore`
- For production deployments, use system environment variables or a secure secrets management service
