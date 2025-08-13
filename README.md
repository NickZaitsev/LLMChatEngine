# 🌸 AI Girlfriend Bot for Telegram 🌸

A professional AI companion bot for Telegram featuring clean architecture, robust error handling, PostgreSQL-backed storage, and multiple LLM provider support. Built with modern Python practices and optimized for production.

## ✨ Features

- **🤖 AI-Powered Conversations**: Clean integration with Azure OpenAI and LM Studio providers
- **💕 Multiple Personalities**: Choose from different personality types (sweet, cheerful, supportive, mysterious)
- **🗄️ PostgreSQL Storage**: Scalable database backend with async SQLAlchemy 2.x
- **🧠 Semantic Memory**: Optional pgvector integration for semantic search of conversation memories
- **💬 Smart Memory Management**: Token-aware message retrieval with conversation context
- **📸 Media Support**: Responds to photos and voice messages
- **⚙️ Professional Architecture**: Clean repository pattern with async interfaces
- **🎭 Interactive Menus**: Intuitive inline keyboards for easy navigation
- **🔧 Production Ready**: Docker support, database migrations, comprehensive logging, and health checks
- **🧪 Comprehensive Testing**: Full test suite with async SQLAlchemy testing

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- LLM Provider API credentials (Azure OpenAI or LM Studio)

### 2. Installation

```bash
# Clone or download this repository
cd ai-girlfriend-bot

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Setup

The bot now uses PostgreSQL for persistent storage. Choose your setup method:

#### Option A: Local PostgreSQL (Recommended)

1. Install PostgreSQL on your system
2. Create a database and user:
```sql
CREATE DATABASE ai_bot_db;
CREATE USER ai_bot_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE ai_bot_db TO ai_bot_user;

-- Optional: Enable pgvector for semantic search
CREATE EXTENSION IF NOT EXISTS pgvector;
```

#### Option B: Docker PostgreSQL (Quick Start)

```bash
# Start PostgreSQL with pgvector support
docker run -d \
  --name ai-bot-postgres \
  -e POSTGRES_DB=ai_bot_db \
  -e POSTGRES_USER=ai_bot_user \
  -e POSTGRES_PASSWORD=your_secure_password \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 4. Configuration

1. Copy `env_example.txt` to `.env`:
```bash
cp env_example.txt .env
```

2. Edit `.env` with your API keys and database connection:
```env
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Database Configuration
DATABASE_URL=postgresql+asyncpg://ai_bot_user:your_secure_password@localhost:5432/ai_bot_db

# For Azure OpenAI
PROVIDER=azure
AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_API_KEY=your_azure_api_key_here
AZURE_MODEL=your_azure_deployment_name

# OR for LM Studio (local)
PROVIDER=lmstudio
LMSTUDIO_MODEL=gpt-3.5-turbo

# Optional: Enable semantic memory search (requires pgvector)
USE_PGVECTOR=true
```

### 5. Database Migration

Initialize the database schema using Alembic:

```bash
# Run database migrations
alembic upgrade head
```

### 6. Run the Bot

```bash
python bot.py
```

### Run with Docker (optional)

```bash
docker compose up --build -d
```

Environment variables are read from your shell or a `.env` file in the project root.

## 🔧 Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Your Telegram bot token | Required |
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `USE_PGVECTOR` | Enable semantic memory search | `false` |
| `PROVIDER` | LLM provider: "azure" or "lmstudio" | `azure` |
| `AZURE_ENDPOINT` | Azure OpenAI endpoint URL | Required for Azure |
| `AZURE_API_KEY` | Azure OpenAI API key | Required for Azure |
| `AZURE_MODEL` | Azure OpenAI deployment name | Required for Azure |
| `LMSTUDIO_MODEL` | LM Studio model name | `gpt-3.5-turbo` |
| `BOT_NAME` | Name of your bot | `Luna` |
| `MAX_TOKENS` | Maximum response length | `3000` |
| `TEMPERATURE` | Response creativity (0.0-1.0) | `0.8` |
| `MAX_CONVERSATION_HISTORY` | Number of messages to remember | `100` |

### Database Configuration Examples

```bash
# Local PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ai_bot_db

# PostgreSQL with custom port
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5433/ai_bot_db

# Remote PostgreSQL (Heroku, Railway, etc.)
DATABASE_URL=postgresql+asyncpg://user:pass@host.railway.app:1234/railway

# For testing (SQLite fallback)
DATABASE_URL=sqlite+aiosqlite:///./test.db
```

### Bot Personalities

- **💕 Sweet & Caring**: Gentle, nurturing, always supportive
- **😊 Cheerful & Energetic**: Happy, optimistic, full of life
- **🤗 Supportive & Understanding**: Wise, empathetic, great listener
- **✨ Mysterious & Alluring**: Intriguing, enigmatic, captivating
- **🔙 Default**: Balanced, caring, affectionate

## 📱 Bot Commands

- `/start` - Start a new conversation
- `/help` - Show help and available commands
- `/clear` - Clear conversation history
- `/stats` - Show chat statistics
- `/personality` - Change bot personality
- `/stop` - End conversation

## 🏗️ Clean Architecture

The application follows professional software engineering practices with a clean repository pattern:

```
bot.py                     # Main bot application
├── config.py             # Configuration with constants and validation
├── ai_handler.py         # Clean AI integration
├── conversation_manager.py  # Legacy memory management (deprecated)
├── memory/               # Advanced memory management system
│   ├── __init__.py       # Memory package interface
│   ├── manager.py        # MemoryManager for episodic memories and summaries
│   ├── embedding.py      # Sentence-transformers integration
│   └── summarizer.py     # LLM and local summarization support
├── storage/              # Database layer
│   ├── __init__.py       # Storage factory and main interface
│   ├── interfaces.py     # Repository protocols and data classes
│   ├── models.py         # SQLAlchemy models with pgvector support
│   └── repos.py          # Async repository implementations
├── migrations/           # Alembic database migrations
│   ├── env.py           # Async migration environment
│   └── versions/        # Migration scripts
├── tests/               # Comprehensive test suite
│   ├── test_memory_manager.py  # Memory system tests
│   └── ...              # Other test files
└── requirements.txt     # Production dependencies with memory dependencies
```

## 🗄️ Database Schema

The PostgreSQL schema is designed for scalability and includes:

### Core Tables
- **users**: User accounts with metadata
- **personas**: AI personality configurations
- **conversations**: Chat sessions linking users and personas
- **messages**: Individual chat messages with token counts
- **memories**: Conversation summaries with optional vector embeddings

### Key Features
- **UUID primary keys** for distributed system compatibility
- **JSONB metadata** fields for flexible data storage
- **Cascading deletes** to maintain referential integrity
- **Optimized indexes** for conversation queries
- **pgvector integration** for semantic memory search (optional)

### Sample Query Performance
```sql
-- Efficiently fetch recent messages within token budget
SELECT * FROM messages
WHERE conversation_id = $1
ORDER BY created_at DESC
LIMIT 50;

-- Semantic memory search (with pgvector)
SELECT * FROM memories
ORDER BY embedding <-> $1
LIMIT 10;
```

## 🤖 Professional LLM Integration


### Clean API Usage
```python
from ai_handler import AIHandler

# Professional initialization with error handling
handler = AIHandler()

# Async generation with timeout and retry logic
response = await handler.generate_response(message, conversation_history)
```

### Production Features:
- **Automatic retries** with exponential backoff
- **Timeout handling** and circuit breaker patterns
- **Rate limit detection** with user-friendly messages
- **Provider abstraction** - switch providers without code changes

## 🗃️ Storage System Usage

### Basic Repository Operations

```python
from storage import create_storage

# Initialize storage
storage = await create_storage(
    db_url="postgresql+asyncpg://user:pass@host/db",
    use_pgvector=True
)

# Create a user and conversation
user = await storage.users.create_user("john_doe")
persona = await storage.personas.create_persona(str(user.id), "Assistant")
conversation = await storage.conversations.create_conversation(
    str(user.id), str(persona.id), "Chat Session"
)

# Store messages
message = await storage.messages.append_message(
    str(conversation.id), "user", "Hello!", token_count=2
)

# Fetch recent messages within token budget
recent = await storage.messages.fetch_recent_messages(
    str(conversation.id), token_budget=1000
)

# Store and search memories (with embeddings)
embedding = [0.1, 0.2, ...] # 384-dimensional vector
memory = await storage.memories.store_memory(
    str(conversation.id), "User likes cats", embedding
)

similar_memories = await storage.memories.search_memories(
    query_embedding=embedding, top_k=5
)

# Cleanup
await storage.close()
```

## 🧠 Memory Management System

The bot includes a sophisticated memory management system that creates episodic memories, generates conversation summaries, and enables semantic retrieval of past conversations.

### Memory Components

- **📝 Episodic Memories**: Automatic chunking and summarization of message histories
- **📊 Summary Rollups**: Intelligent merging of episodic memories into conversation profiles
- **🔍 Semantic Retrieval**: Vector-based search for relevant memories using embeddings
- **🤖 Dual Summarization**: Support for both LLM-based and local transformer summarization

### MemoryManager Configuration

```python
from memory import MemoryManager
from storage import create_storage

# Initialize storage
storage = await create_storage(
    db_url="postgresql+asyncpg://user:pass@host/db",
    use_pgvector=True
)

# Configure memory manager
config = {
    # Embedding model configuration
    "embed_model": "sentence-transformers/all-MiniLM-L6-v2",
    
    # Summarization mode: "llm" or "local"
    "summarizer_mode": "llm",
    
    # For LLM mode: provide async summarization function
    "llm_summarize": your_llm_summarize_function,
    
    # For local mode: specify HuggingFace model
    "local_model": "facebook/bart-large-cnn",
    
    # Chunking configuration
    "chunk_overlap": 2  # Messages overlapping between chunks
}

# Create memory manager
memory_manager = MemoryManager(
    message_repo=storage.messages,
    memory_repo=storage.memories,
    conversation_repo=storage.conversations,
    config=config
)
```

### Memory Operations

#### Create Episodic Memories
```python
# Process conversation into episodic memory chunks
memories = await memory_manager.create_episodic_memories(
    conversation_id="conv-uuid",
    chunk_size_messages=15  # Messages per chunk
)

# Each memory contains structured data:
# - summary_text: AI-generated summary
# - key_facts: Extracted important facts
# - importance: 0.0-1.0 importance score
# - source_message_ids: Original message references
# - embeddings: Vector representation for search
```

#### Generate Summary Rollups
```python
# Create or update conversation summary
summary = await memory_manager.rollup_summary(
    conversation_id="conv-uuid"
)

# Summary intelligently merges:
# - Previous conversation profile
# - New episodic memories
# - Change tracking for transparency
```

#### Semantic Memory Retrieval
```python
# Find relevant memories using natural language queries
relevant_memories = await memory_manager.retrieve_relevant_memories(
    query_text="What did we discuss about machine learning?",
    top_k=6  # Number of results
)

# Returns MemoryRecord objects with:
# - Original memory content
# - Similarity scores
# - Metadata (importance, language, source messages)
```

### Memory Configuration Keys

| Configuration Key | Description | Default | Mode |
|-------------------|-------------|---------|------|
| `embed_model` | Sentence-transformers model for embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Both |
| `summarizer_mode` | Summarization method: "llm" or "local" | `llm` | Both |
| `llm_summarize` | Async function for LLM summarization | Required | LLM |
| `local_model` | HuggingFace model for local summarization | `facebook/bart-large-cnn` | Local |
| `chunk_overlap` | Overlapping messages between chunks | `2` | Both |

### LLM Summarization Function

For LLM mode, provide an async function with this signature:

```python
async def llm_summarize(text: str, mode: str) -> str:
    """
    Custom LLM summarization function.
    
    Args:
        text: Text to summarize or merge
        mode: "summarize" for chunks, "merge" for rollups
        
    Returns:
        Summary text or merged profile
    """
    if mode == "summarize":
        # Return structured JSON for episodic memories
        return json.dumps({
            "summary": "Conversation about...",
            "key_facts": ["fact1", "fact2"],
            "importance": 0.8,
            "language": "en"
        })
    elif mode == "merge":
        # Return merged profile text
        return "Updated conversation profile..."
```

### Memory Dependencies

The memory system requires additional dependencies:

```bash
# Install memory management dependencies
pip install sentence-transformers>=2.2.2
pip install transformers>=4.30.0
pip install torch>=2.0.0
pip install numpy>=1.24.0
```

### Memory Storage Format

Memories are stored as structured JSON in the database:

```json
{
  "summary": "User discussed their interest in AI and machine learning",
  "key_facts": ["Prefers Python for ML", "Learning about transformers"],
  "importance": 0.8,
  "source_message_ids": ["msg-1", "msg-2", "msg-3"],
  "lang": "en",
  "content_hash": "abc123def",
  "chunk_index": 0,
  "created_at": "2024-01-01T12:00:00Z"
}
```

### Performance Considerations

- **Batched Processing**: Embeddings are generated in batches for efficiency
- **Deduplication**: Identical content is detected and skipped using content hashes
- **Async Operations**: All memory operations are fully async and non-blocking
- **Vector Search**: Uses pgvector for fast similarity search when available
- **Token Awareness**: Integrates with existing token budget management

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Install test dependencies
pip install pytest pytest-asyncio aiosqlite

# Run all tests
pytest

# Run with coverage
pytest --cov=storage --cov-report=html

# Run specific test files
pytest tests/test_message_repo.py -v
pytest tests/test_memory_repo.py -v
pytest tests/test_storage_factory.py -v
pytest tests/test_memory_manager.py -v

# Run memory management tests specifically
pytest tests/test_memory_manager.py::TestMemoryManagerInit -v
pytest tests/test_memory_manager.py::TestEpisodicMemoryCreation -v
```

### Test Database
Tests use SQLite in-memory databases for speed and isolation. No external database required for testing.

## 🔧 Database Management

### Migration Commands

```bash
# Create a new migration
alembic revision --autogenerate -m "Add new feature"

# Apply migrations
alembic upgrade head

# Downgrade one revision
alembic downgrade -1

# Show migration history
alembic history

# Show current revision
alembic current
```

### Backup and Restore

```bash
# Backup database
pg_dump ai_bot_db > backup.sql

# Restore database
psql ai_bot_db < backup.sql
```

## 🚨 Troubleshooting

### Common Issues

**Database Connection Failed**
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Test connection manually
psql postgresql://user:pass@host:5432/dbname
```

**pgvector Extension Missing**
```sql
-- Connect as superuser and run:
CREATE EXTENSION IF NOT EXISTS pgvector;
```

**Migration Conflicts**
```bash
# Reset migrations (DANGER: loses data)
alembic downgrade base
alembic upgrade head
```

**Token Estimation Issues**
```python
# The system uses tiktoken if available, falls back to heuristics
pip install tiktoken  # For accurate token counting
```

### Performance Tuning

**Message Query Performance**
```sql
-- Ensure these indexes exist
CREATE INDEX CONCURRENTLY ON messages (conversation_id, created_at DESC);
CREATE INDEX CONCURRENTLY ON messages (conversation_id, role);
```

**Memory Search Performance (pgvector)**
```sql
-- Tune IVFFlat index for your data size
DROP INDEX ix_memories_embedding;
CREATE INDEX ON memories USING ivfflat (embedding) WITH (lists = 1000);
```

## 🔒 Security & Privacy

- **API Keys**: Never commit your `.env` file to version control
- **Database Security**: Use strong passwords and connection encryption
- **User Data**: Conversations stored in PostgreSQL with proper constraints
- **Privacy**: The bot only processes messages you send to it
- **Rate Limiting**: Built-in handling for API rate limits
- **Local Option**: Use LM Studio for complete privacy and offline operation
- **Data Isolation**: Each conversation is properly isolated using foreign keys

## 🚀 Production Deployment

### Environment Setup
```bash
# Install production dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://..."
export TELEGRAM_TOKEN="your_token"

# Run migrations
alembic upgrade head

# Start bot
python bot.py
```

### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up --build -d

# View logs
docker-compose logs -f bot
```

### Health Checks
```python
# The storage system includes health checks
health = await storage.health_check()
assert health == True
```

## 🪪 License

Released under the MIT License. See `LICENSE` for details.