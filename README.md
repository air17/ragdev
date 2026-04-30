# RAG Development Project

This project implements a coding assistant delivered via a Telegram bot. The retrieval mechanism is **grep-based search** (ripgrep) for robust and exact code retrieval. Vector embeddings (Milvus + Gemini) were part of the original design but are now **deprecated** and no longer used by the agent.

## Features

- **Grep-based Code Search**: Core retrieval capability — fast, exact, regex-aware
- **Telegram Bot Interface**: Interact with the system directly via Telegram
- **Agentic Loop**: `ChatAgent` drives a multi-turn tool-use loop over DeepSeek LLM

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

Required variables:

| Variable | Description |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API key for the LLM |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `MILVUS_ENDPOINT` | *(Deprecated)* Milvus cluster endpoint |
| `MILVUS_TOKEN` | *(Deprecated)* Milvus authentication token |
| `GEMINI_API_KEY` | *(Deprecated)* Gemini API key for embeddings |

> `MILVUS_*` and `GEMINI_API_KEY` are only required if using the deprecated `rag/` modules directly. The bot itself no longer needs them.

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

```
chat/           Core agent logic (ChatAgent) and session persistence
agent_tools/    Tool implementations: grep, read_file, file_list, llms
telegram_bot/   aiogram v3 Telegram bot: auth, routing, scheduling
project_management/  Registry of external projects and git helpers
rag/            DEPRECATED — Milvus + Gemini vector embedding code
config.py       Centralised configuration (reads .env then system env)
requirements.txt  Project dependencies
```

### Key files

- `chat/agent.py` — `ChatAgent`: full agentic loop, tool dispatch, message history
- `chat/const.py` — `SYSTEM_PROMPT` template
- `project_management/const.py` — `PROJECTS` registry
- `telegram_bot/middleware.py` — `DatabaseMiddleware`: RBAC, fail-open design
- `telegram_bot/db.py` — `AsyncUserDatabase` using SQLModel/SQLAlchemy + Alembic

## Database Migrations

The bot uses SQLite through SQLModel/SQLAlchemy, with Alembic as the migration
system. `AsyncUserDatabase.initialize()` runs migrations on startup.

For a fresh DB, either start the bot or run:

```bash
python3 -m alembic upgrade head
```

For an existing legacy DB from the old `MigrationManager` version 2, back up the
DB first. On startup, the bot validates the existing tables and stamps Alembic to
the current revision without recreating tables. The manual equivalent is:

```bash
python3 -m alembic stamp head
```

For future schema changes, edit the SQLModel models, generate and review a
migration, then apply it:

```bash
python3 -m alembic revision --autogenerate -m "describe change"
python3 -m alembic upgrade head
```

## Testing

This project uses pytest for testing. Tests are organized in a modular structure:

- Project-level tests in the `tests/` directory
- Module-specific tests in `agent_tools/tests/`, `chat/tests/`, and `telegram_bot/tests/`

### Running Tests

To run all tests:

```bash
pytest
```

To run tests for a specific module:

```bash
pytest agent_tools/tests/
pytest chat/tests/
pytest telegram_bot/tests/
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

## Deprecated: Milvus & Vector Embeddings (`rag/`)

> **These modules are deprecated.** They are no longer used by `ChatAgent` and will be removed in a future version. All public symbols emit a `DeprecationWarning` at runtime.

The `rag/` package contains the original vector-based retrieval strategy:

| Module | Status |
|---|---|
| `rag/embeddings.py` — `EmbeddingManager` | Deprecated |
| `rag/snippet_reader.py` — `read_snippets` | Deprecated |
| `rag/reranker.py` — `rerank_results` | Deprecated |
| `rag/chunker.py` — `chunk_file` | Deprecated |
| `rag/code_indexer.py` — `index`, `process_directory` | Deprecated |

Similarly, `agent_tools/file_list.py:search_files_recursive` is deprecated and not exposed as an agent tool.
