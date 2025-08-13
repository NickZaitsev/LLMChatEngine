# 🌸 AI Girlfriend Bot for Telegram 🌸

A professional AI companion bot for Telegram featuring clean architecture, robust error handling, and multiple LLM provider support. Built with modern Python practices and optimized for performance.

## ✨ Features

- **🤖 AI-Powered Conversations**: Clean integration with Azure OpenAI and LM Studio providers
- **💕 Multiple Personalities**: Choose from different personality types (sweet, cheerful, supportive, mysterious)
- **💬 Smart Memory Management**: Optimized conversation history with token-aware trimming
- **📸 Media Support**: Responds to photos and voice messages
- **⚙️ Professional Architecture**: Clean separation of concerns and robust error handling
- **🎭 Interactive Menus**: Intuitive inline keyboards for easy navigation
- **🔧 Production Ready**: Docker support, comprehensive logging, and health checks

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

### 3. Configuration

1. Copy `env_example.txt` to `.env`:
```bash
cp env_example.txt .env
```

2. Edit `.env` with your API keys:
```env
TELEGRAM_TOKEN=your_telegram_bot_token_here

# For Azure OpenAI
PROVIDER=azure
AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_API_KEY=your_azure_api_key_here
AZURE_MODEL=your_azure_deployment_name

# OR for LM Studio (local)
PROVIDER=lmstudio
LMSTUDIO_MODEL=gpt-3.5-turbo
```

### 4. Run the Bot

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
| `PROVIDER` | LLM provider: "azure" or "lmstudio" | `azure` |
| `AZURE_ENDPOINT` | Azure OpenAI endpoint URL | Required for Azure |
| `AZURE_API_KEY` | Azure OpenAI API key | Required for Azure |
| `AZURE_MODEL` | Azure OpenAI deployment name | Required for Azure |
| `LMSTUDIO_MODEL` | LM Studio model name | `gpt-3.5-turbo` |
| `BOT_NAME` | Name of your bot | `Luna` |
| `MAX_TOKENS` | Maximum response length | `3000` |
| `TEMPERATURE` | Response creativity (0.0-1.0) | `0.8` |
| `MAX_CONVERSATION_HISTORY` | Number of messages to remember | `100` |

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

The application follows professional software engineering practices:

```
bot.py                     # Main bot application 
├── config.py             # Configuration with constants and validation
├── ai_handler.py         # Clean AI integration
├── conversation_manager.py  # Optimized memory management
└── requirements.txt      # Minimal dependencies
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

## 🔒 Security & Privacy

- **API Keys**: Never commit your `.env` file to version control
- **User Data**: Conversations are stored locally
- **Privacy**: The bot only processes messages you send to it
- **Rate Limiting**: Built-in handling for API rate limits
- **Local Option**: Use LM Studio for complete privacy and offline operation

## 🪪 License

Released under the MIT License. See `LICENSE` for details.