# AGENTS.md — ragdev coding assistant

## Architecture

Telegram bot → `BotEventHandler` (aiogram v3) → `ChatAgent` (agentic loop) → DeepSeek LLM (OpenAI-compatible API) + tool dispatch

**Key files:**
- `chat/agent.py` — `ChatAgent`: full tool-use loop, `dispatch_tool_call`, hard limit of 15 iterations
- `chat/sessions.py` — `ChatSessionManager`: session history persisted as **pickle files** in `sessions/` dir
- `telegram_bot/event_handler.py` — all bot command/message handlers, `BotEventHandler`
- `telegram_bot/middleware.py` — `DatabaseMiddleware`: RBAC + user auto-registration, **fail-open** (DB errors never block handlers)
- `telegram_bot/db.py` — `AsyncUserDatabase`: async SQLite via SQLModel/SQLAlchemy + Alembic migrations
- `project_management/const.py` — `PROJECTS` dict: maps project slug → local path + prompt + submodules
- `config.py` — central config; reads `.env` first, then system env, then defaults
- `rag/` — **deprecated**; all symbols emit `DeprecationWarning`. Do not add new code here.

## Adding a New Project

Register it in `project_management/const.py:PROJECTS`. The bot auto-registers `/project_slug` as a Telegram command via dynamic handler registration in `BotEventHandler.setup_handlers()` — no other changes needed.

## Sessions: Two-Layer Persistence

1. **Pickle file** (`sessions/<uuid>.pickle`): stores full OpenAI message history + meta (project_dir, submodules, repo_url, total_tokens).
2. **SQLite `chat_sessions` table**: stores session metadata per user for bot UI (name, message_count, last_activity).
   Schema changes are managed by Alembic.

When message history exceeds limits or gets corrupted, `ChatSessionManager.fix_messages_after_interruption()` trims to the last assistant message.

## Agent Tools

Registered tools (see `chat/agent.py:__init__`):
- `grep_search` → `agent_tools/grep.py:search_codebase` — ripgrep, max 50 results, excludes `tests/`, `__*__/`, hidden files
- `read_file` / `scroll_up` / `scroll_down` → `agent_tools/read_file.py`, 250 lines per call
- `list_dir` → `agent_tools/file_list.py:ls`
- `terminal` → always returns unavailable (placeholder, never executes)

`agent_tools/file_list.py:search_files_recursive` is deprecated and not exposed as a tool.

## RBAC

New users default to `is_active=False`. A superadmin must `/activate <user_id>`. Roles: `user`, `superadmin`. `DatabaseMiddleware` is **fail-open**: any DB exception during auth continues to the handler (logged but not raised).

## Environment

Required in `.env`:
- `DEEPSEEK_API_KEY` — LLM access (DeepSeek via OpenAI-compatible API)
- `TELEGRAM_BOT_TOKEN`

Deprecated (only needed if using `rag/` directly):
- `MILVUS_ENDPOINT`, `MILVUS_TOKEN`, `GEMINI_API_KEY`

## Commands

```bash
# Run the bot
python -c "import asyncio; from telegram_bot.main import setup_production_bot; asyncio.run(setup_production_bot())"

# Run all tests
pytest

# Run module tests
pytest agent_tools/tests/
pytest chat/tests/
pytest telegram_bot/tests/

# Apply DB migrations manually
python -m alembic upgrade head

# Generate a new migration after editing SQLModel models
python -m alembic revision --autogenerate -m "describe change"

# Install pre-commit hooks (runs ruff + tests on push)
pip install pre-commit && pre-commit install
```

## Conventions

- **Always use top-level imports** — no inline/deferred imports anywhere in the codebase.
- Linter/formatter: `ruff` (auto-fix on commit via pre-commit).
- Git commits: use conventional commits style (e.g. `feat: add new agent tool for X`, `fix: handle DB error in middleware`, `docs: update AGENTS.md with new conventions`).
- Always use typing hints everywhere, including function signatures and variable declarations. For dicts declare `TypedDict` in `types.py` and import from there. Always use modern typing syntax (PEP 585+); no `from typing import List` etc.
- Async tests use `pytest-asyncio`; see `agent_tools/tests/conftest.py` for fixtures.
- All bot response text constants live in `telegram_bot/const.py`.
- `chat/const.py:SYSTEM_PROMPT` accepts `{project_tree}`, `{project_prompt}`, and `{repo_url}` format placeholders.
- After implementing a feature, add a test in the appropriate `tests/` dir and ensure it runs before committing. Also run all the tests to ensure nothing is broken.
- After implementing an edit, propose a commit message for it
