# LLMChatEngine

A powerful, production-ready LLM chat engine with advanced memory management, semantic search, and multi-provider support. Built with modern Python practices and optimized for scalable conversational AI applications.

## Features

- **Multi-LLM Provider Support**: Clean integration with Azure OpenAI, LM Studio, and other LLM providers
- **Advanced Memory Management**: LlamaIndex-based memory system with semantic search via pgvector and automated conversation summarization
- **PostgreSQL Storage**: Scalable database backend with async SQLAlchemy 2.x and pgvector extension
- **Production Ready**: Multi-stage Docker build, database migrations, comprehensive logging
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
git clone https://github.com/your-repo/llm-chat-engine.git
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
PROVIDER=azure                                    # Options: "azure" or "lmstudio"
AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_API_KEY=your_azure_api_key_here
AZURE_MODEL=your_azure_deployment_name

# LM Studio Configuration (alternative to Azure)
LMSTUDIO_MODEL=your_model
LMSTUDIO_BASE_URL=http://host-machine:1234/v1
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
- **AI Handler**: Orchestrates LLM interactions across multiple providers with retry logic and timeout handling
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

## Development

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_memory_manager.py
```

### Code Quality
- Pre-commit hooks configured
- Black for code formatting
- Ruff for linting
- MyPy for type checking

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.