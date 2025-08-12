# 🌸 AI Girlfriend Bot for Telegram 🌸

A sophisticated AI companion bot for Telegram that uses GitHub's API with DeepSeek and other models to provide engaging, personalized conversations with a romantic and supportive personality.

## ✨ Features

- **🤖 AI-Powered Conversations**: Uses GitHub's API with DeepSeek, Claude, and other models for natural, contextual responses
- **💕 Multiple Personalities**: Choose from different personality types (sweet, cheerful, supportive, mysterious)
- **💬 Conversation Memory**: Remembers chat history for contextual conversations
- **📸 Media Support**: Responds to photos and voice messages
- **⚙️ Customizable Settings**: Adjust response length, temperature, and conversation history
- **🎭 Interactive Menus**: Beautiful inline keyboards for easy navigation

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- GitHub Personal Access Token (for API access to models like DeepSeek)

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
GITHUB_TOKEN=your_github_token_here
GITHUB_MODEL=deepseek/DeepSeek-V3-0324
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
| `GITHUB_TOKEN` | Your GitHub Personal Access Token | Required |
| `GITHUB_MODEL` | Model to use (deepseek-chat, claude-3, etc.) | `deepseek/DeepSeek-V3-0324` |
| `BOT_NAME` | Name of your bot | `Luna` |
| `MAX_TOKENS` | Maximum response length | `150` |
| `TEMPERATURE` | Response creativity (0.0-1.0) | `0.8` |
| `MAX_CONVERSATION_HISTORY` | Number of messages to remember | `10` |

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

## 🏗️ Architecture

```
bot.py                 # Main bot application
├── config.py         # Configuration management
├── ai_handler.py     # GitHub API integration
├── conversation_manager.py  # Chat history management
└── requirements.txt  # Python dependencies
```

## 🔒 Security & Privacy

- **API Keys**: Never commit your `.env` file to version control
- **User Data**: Conversations are stored locally
- **Privacy**: The bot only processes messages you send to it
- **Rate Limiting**: Built-in handling for GitHub API rate limits

## 🪪 License

Released under the MIT License. See `LICENSE` for details.