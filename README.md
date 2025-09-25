# AI Girlfriend Bot for Telegram

A professional AI companion bot for Telegram featuring PostgreSQL-backed storage, semantic memory, and multiple LLM provider support. Built with modern Python practices and optimized for production.

## Features

- **AI-Powered Conversations**: Clean integration with Azure OpenAI and LM Studio providers
- **PostgreSQL Storage**: Scalable database backend with async SQLAlchemy 2.x
- **Production Ready**: Docker support, database migrations, comprehensive logging
- **Docker Architecture**: PostgreSQL, Redis, Celery workers, and backup services

## Quick Start with Docker

### Prerequisites

- Docker Engine (20.10.0 or higher)
- Docker Compose (v2.0.0 or higher)
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- LLM Provider API credentials (Azure OpenAI or LM Studio)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-repo/ai-girlfriend-bot.git
cd ai-girlfriend-bot
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
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Database Configuration
DATABASE_URL=postgresql+asyncpg://ai_bot:your_secure_password@postgres:5432/ai_bot
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
Gemma 3 recommended.

### Usage

Start the bot using Docker Compose:

```bash
docker-compose up --build -d
```

This will start all required services:
- The main bot application
- PostgreSQL database with pgvector support
- Redis for message queuing and proactive messaging
- Celery worker for background tasks
- PostgreSQL backup service

To view logs:
```bash
docker-compose logs -f ai-girlfriend-bot
```

To stop the services:
```bash
docker-compose down
```

## Bot Commands

- `/start` - Start a new conversation
- `/help` - Show help and available commands
- `/clear` - Clear conversation history
- `/stats` - Show chat statistics
- `/personality` - Change bot personality
- `/status` - Check bot health
- `/ping` - Quick health check

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.