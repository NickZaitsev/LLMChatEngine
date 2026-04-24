# LLMChatEngine

A modular LLM chat engine with advanced memory management, semantic search, and multi-provider support. Built with modern Python practices and designed for scalable conversational AI applications.

## Features

- **Multi-LLM Provider Support**: Clean integration with Azure OpenAI, LM Studio, and other LLM providers
- **Advanced Memory Management**: LlamaIndex-based memory system with semantic search via pgvector and automated conversation summarization
- **PostgreSQL Storage**: Scalable database backend with async SQLAlchemy 2.x and pgvector extension
- **Deployment Ready**: Multi-stage Docker build, database migrations, comprehensive logging, and GitHub Actions checks
- **Modular Architecture**: Extensible design for different chat platforms and interfaces
- **Message Buffering**: Intelligent message buffering to capture complete user thoughts
- **Proactive Features**: Scheduled messaging with Celery Beat and automated conversation management
- **Centralized App Context**: Singleton pattern for shared service initialization and management
- **Conversation Summarization**: Automatic periodic summarization of long conversations using Celery tasks

## Quick Start with Docker

### Prerequisites

- Docker Engine (20.10.0 or higher)
- Docker Compose (v2.0.0 or higher)
- LLM Provider API credentials (Azure OpenAI or LM Studio)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-user/llm-chat-engine.git
cd llm-chat-engine
```

2. Create a `.env` file from the example:
```bash
cp env_example.txt .env
```

3. Edit the `.env` file with your API keys and configuration:
```bash
nano .env
```

### Configuration

Edit the `.env` file with your specific configuration:

```env
# Database Configuration
DATABASE_URL=postgresql+asyncpg://llm_engine:your_secure_password@postgres:5432/llm_engine
DB_PASSWORD=your_secure_password_here
USE_PGVECTOR=true

# LLM Provider Configuration
PROVIDER=azure                                    # Options: "azure", "lmstudio", or "gemini"
AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_API_KEY=your_azure_api_key_here
AZURE_MODEL=your_azure_deployment_name

# LM Studio Configuration (alternative to Azure)
LMSTUDIO_MODEL=your_model
LMSTUDIO_BASE_URL=http://host-machine:1234/v1

# Gemini Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-pro
GEMINI_EMBEDDING_MODEL=models/embedding-001
```

Gemma 3 recommended for optimal performance.

### Usage

Start the engine using Docker Compose:

```bash
docker-compose up --build -d
```

This will start all required services:
- The main chat engine application
- PostgreSQL database with pgvector support
- Redis for message queuing and background tasks
- Celery worker for background processing
- PostgreSQL backup service

To view logs:
```bash
docker-compose logs -f llm-chat-engine
```

To stop the services:
```bash
docker-compose down
```

## Architecture Overview

LLMChatEngine provides a modular architecture that can be adapted for various chat platforms:

- **App Context**: Singleton pattern for centralized service initialization and management
- **AI Handler**: Orchestrates LLM interactions across multiple providers (Azure, LM Studio, Gemini) with retry logic and timeout handling
- **Memory Manager**: LlamaIndex-based system for creating and managing semantic memories with vector search
- **Prompt Assembler**: Constructs contextual prompts integrating conversation history, memories, and summaries
- **Message Manager**: Handles message queuing and ordered delivery with interaction indicators
- **Buffer Manager**: Buffers user input for coherent processing and complete thought capture
- **Storage Layer**: PostgreSQL with pgvector extension for persistent data management and vector storage
- **Proactive Messaging**: Celery Beat-based system for scheduled user engagement and automated messaging
- **Conversation Summarization**: Celery-based periodic summarization of long conversations to manage context length

![Architecture Diagram](docs/architecture.png)

## API Integration

The engine can be integrated with various chat platforms through its modular interface design. Current implementation includes Telegram bot support, with extensible architecture for additional platforms.

## Multi-Bot Setup & Usage

The system now supports running multiple AI bots simultaneously, managed by a central Admin Bot.

### 1. Admin Bot Setup
1.  **Create Admin Bot**: Talk to [@BotFather](https://t.me/BotFather) on Telegram and create a new bot (e.g., `MyAdminBot`). Get the **token**.
2.  **Get Your User ID**: Talk to [@userinfobot](https://t.me/userinfobot) to get your numerical Telegram User ID (e.g., `123456789`).
3.  **Generate Encryption Key**: Run the following Python snippet to generate a secure key for token encryption:
    ```python
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
    ```

### 2. Configuration
Add the following to your `.env` file:

```env
# Admin Bot Configuration
ADMIN_BOT_TOKEN=your_admin_bot_token_here
ADMIN_USER_IDS=123456789,987654321  # Comma-separated list of authorized admin IDs
TOKEN_ENCRYPTION_KEY=your_generated_key_here
```

### 3. Running the System
Update your Docker containers:
```bash
docker-compose up --build -d
```
This will start the `AdminBot` and the `BotManager`.

### 4. Managing Bots
Open your Admin Bot in Telegram and use these commands:

- **/addbot**: Start a wizard to add a new user bot. You will need:
    - The new bot's token (from BotFather).
    - A name for the bot.
    - A personality/system prompt.
- **/listbots**: View all running bots and their status.
- **/setprompt <bot_id>**: Update a bot's personality on the fly.
- **/togglefeature <bot_id> <feature>**: Enable/disable features (e.g., `VOICE_MESSAGES`, `MEMORY`).
- **/removebot <bot_id>**: Stop and remove a bot.

## Development

### Testing
```bash
# Create and use the pinned project environment
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt

# Run all tests
.\.venv\Scripts\python -m pytest

# Run with coverage
.\.venv\Scripts\python -m pytest --cov=.

# Run specific test file
.\.venv\Scripts\python -m pytest tests/test_memory_manager.py
```

### Code Quality
```bash
# Install development tooling
pip install -r requirements-lock.txt

# Run linting and formatting checks
ruff check .

# Run pre-commit hooks
pre-commit run --all-files
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
