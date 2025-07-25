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

### Indexing Code Files

To index Python files in a directory:

```python
from main import index

# Index files in the current directory
index()

# Index files in a specific directory
index(directory="/path/to/your/code")
```

This will:
1. Create a Milvus collection (or reset an existing one)
2. Process all Python files in the specified directory
3. Chunk the files into manageable segments
4. Generate embeddings for each chunk
5. Store the embeddings and metadata in Milvus

### Retrieving Similar Code

To retrieve code chunks similar to a query:

```python
from embeddings import EmbeddingManager

# Initialize the embedding manager
manager = EmbeddingManager(collection_name="ragdev")

# Retrieve vectors for a question
results = manager.retrieve_vectors_for_question(
    question="How do I parse Python files?",
    top_k=5  # Number of results to return
)

# Process the results
for result in results[0]:
    print(f"File: {result['filename']}, Lines: {result['start_line']}-{result['end_line']}")
    print(f"Similarity score: {result['score']}")
    # You can now load the file and extract the relevant lines
```

## Configuration Management

The project uses a centralized configuration system:

- Environment variables are loaded from the `.env` file if it exists
- If a variable is not found in the `.env` file, it falls back to system environment variables
- Default values are provided as a last resort (not recommended for production)

## Project Structure

- `main.py`: Main entry point for indexing files
- `chunker.py`: Handles parsing and chunking of Python files
- `embeddings.py`: Manages vector embeddings and Milvus operations
- `config.py`: Centralizes configuration management
- `requirements.txt`: Lists project dependencies

## Security Notes

- Never commit your `.env` file to version control
- The `.env` file is already included in `.gitignore`
- For production deployments, use system environment variables or a secure secrets management service

## License

[Specify your license here]

## Contributing

[Add contribution guidelines if applicable]