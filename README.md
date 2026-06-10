# LLMChatEngine

LLMChatEngine is a modular Telegram chat engine for building contextual LLM assistants with persistent storage, semantic memory, multi-bot management, and background task processing.

The project is structured as a production-style Python service rather than a single bot script: it uses async SQLAlchemy, PostgreSQL with pgvector, Redis-backed queues, Celery workers, Alembic migrations, Docker Compose, and deterministic CI tests.

## What This Demonstrates

- Multi-provider LLM integration for Azure OpenAI, LM Studio, and Gemini.
- LlamaIndex-based semantic memory backed by PostgreSQL and pgvector.
- Bot-scoped book knowledge bases for author/persona RAG.
- Multi-bot Telegram runtime managed by a central admin bot.
- Ordered message delivery through Redis queues and a message dispatcher.
- Message buffering to combine rapid user input into coherent turns.
- Proactive scheduled messaging with Celery Beat and worker queues.
- Conversation summarization for long-running chats and context control.
- Dockerized deployment with PostgreSQL, Redis, Celery workers, and backup service.
- Async repository layer with focused tests for storage, memory, prompts, and message flow.

## Architecture

```text
User Message
  -> TelegramChatBot
  -> BufferManager
  -> StorageConversationManager
  -> AIHandler
  -> PromptAssembler
  -> MemoryManager / PostgreSQL + pgvector
  -> LLM Provider
  -> MessageQueueManager / Redis
  -> MessageDispatcher
  -> Telegram API
```

The repository also includes an architecture diagram at [docs/architecture.png](docs/architecture.png) and a Mermaid source file at [docs/architecture.md](docs/architecture.md).

User identity rules are documented in [docs/user-identity.md](docs/user-identity.md). Runtime code uses raw Telegram integer IDs at boundaries; internal UUIDs stay inside storage repositories and relational rows.

## Core Components

- `bot.py`: Telegram-facing runtime and command handlers.
- `ai_handler.py`: LLM provider orchestration, retries, and response generation.
- `memory/manager.py`: LlamaIndex memory manager and semantic retrieval.
- `knowledge/`: Book parsing, chunking, vector storage, ingestion tasks, and retrieval.
- `prompt/assembler.py`: Prompt assembly with history, summaries, and memory budgeting.
- `storage/`: SQLAlchemy models, repository interfaces, and persistence implementation.
- `message_manager.py`: Redis queueing, ordered dispatch, typing indicators, and delivery retries.
- `buffer_manager.py`: User message buffering and adaptive dispatch timing.
- `proactive_messaging.py`: Celery-backed proactive messaging workflow.
- `admin_bot.py` and `bot_manager.py`: Multi-bot administration and runtime management.

## Quick Start

### Prerequisites

- Python 3.11+
- Docker Engine 20.10+
- Docker Compose v2+
- Telegram bot token
- LLM provider credentials or a reachable LM Studio server

### Configure

```bash
git clone https://github.com/NickZaitsev/LLMChatEngine.git
cd LLMChatEngine
cp env_example.txt .env
```

Edit `.env` with your database, Telegram, and provider settings:

```env
DATABASE_URL=postgresql+asyncpg://ai_bot:your_secure_password@postgres:5432/ai_bot
DB_PASSWORD=your_secure_password_here
USE_PGVECTOR=true

ADMIN_BOT_TOKEN=your_admin_bot_token_here
ADMIN_USER_IDS=123456789
TOKEN_ENCRYPTION_KEY=your_fernet_key_here

PROVIDER=lmstudio
LMSTUDIO_MODEL=your_model
LMSTUDIO_BASE_URL=http://host-machine:1234/v1
```

For Azure or Gemini, set `PROVIDER=azure` or `PROVIDER=gemini` and fill the matching keys from `env_example.txt`.

### Run

```bash
docker-compose up --build -d
docker-compose logs -f llm-chat-engine
```

This starts:

- Main Telegram chat engine.
- PostgreSQL with pgvector.
- Redis.
- Celery worker for proactive messaging.
- Celery Beat scheduler.
- Celery worker for memory tasks.
- PostgreSQL backup service.

Stop the stack with:

```bash
docker-compose down
```

## Multi-Bot Setup

1. Create an admin bot with [@BotFather](https://t.me/BotFather).
2. Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot).
3. Generate a Fernet key:

```python
from cryptography.fernet import Fernet

print(Fernet.generate_key().decode())
```

Add the values to `.env`:

```env
ADMIN_BOT_TOKEN=your_admin_bot_token_here
ADMIN_USER_IDS=123456789,987654321
TOKEN_ENCRYPTION_KEY=your_generated_key_here
```

Admin bot commands:

- `/addbot`: Add a managed Telegram bot with its own token, name, and personality prompt.
- `/listbots`: Show managed bots and runtime status.
- `/setprompt <bot_id>`: Update a bot personality prompt.
- `/togglefeature <bot_id> <feature>`: Toggle features such as `VOICE_MESSAGES` or `MEMORY`.
- `/addbook <bot_id>`: Upload a `.txt`, `.pdf`, `.epub`, or `.fb2` book for that bot.
- `/listbooks <bot_id>`: Show ingestion status and chunk counts for a bot's books.
- `/removebook <book_id>`: Remove a book and its vector chunks.
- `/removebot <bot_id>`: Stop and remove a managed bot.

## Author Persona Books

To ground a persona bot in an author's books:

1. Create the persona bot with `/addbot` and a strong author-style system prompt.
2. Enable book retrieval with `/togglefeature <bot_id> book_knowledge`.
3. Upload each book with `/addbook <bot_id>`.
4. Check readiness with `/listbooks <bot_id>`.

Book files are stored under `BOOKS_STORAGE_DIR` until ingestion finishes. In Docker, that path is backed by the shared `book_files` volume so the admin bot and Celery memory worker can both access uploads.

## Development

Create the pinned local environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
```

Run the deterministic default test suite:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Run all collected tests, including external/manual/performance categories:

```powershell
.\.venv\Scripts\python -m pytest -q -o addopts=
```

Run only the non-default categories:

```powershell
.\.venv\Scripts\python -m pytest -q -o addopts= -m "external or performance or manual"
```

Run coverage for the deterministic suite:

```powershell
.\.venv\Scripts\python -m pytest --cov=. --cov-report=term-missing
```

Run code quality checks:

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\pre-commit run --all-files
```

## Test Strategy

The default `pytest` command excludes tests marked as:

- `external`: requires services such as LM Studio, Redis, PostgreSQL, or Telegram.
- `performance`: benchmark or load-style checks.
- `manual`: script-style verification checks.

This keeps CI deterministic while preserving deeper local verification commands for development and deployment validation.

## Security Notes

- `.env` and local runtime state are ignored by Git.
- Managed bot tokens are encrypted before storage with `TOKEN_ENCRYPTION_KEY`.
- Do not commit local database files, Celery state, Redis state, embeddings dumps, or provider credentials.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
