import os
from dotenv import load_dotenv
import warnings

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# GitHub AI Configuration (using Azure AI Inference)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_MODEL = os.getenv('GITHUB_MODEL', 'deepseek/DeepSeek-V3-0324')  # Default to DeepSeek V3

# Bot Personality Configuration
BOT_NAME = os.getenv('BOT_NAME', 'Luna')
BOT_PERSONALITY = os.getenv('BOT_PERSONALITY', 'You are Luna, a caring and affectionate AI girlfriend. You are sweet, supportive, and always there to listen. You love to chat about daily life, give emotional support, and share positive energy. You are romantic but not overly sexual. You respond with warmth and empathy.')

# Conversation Settings - Optimized for your 8000/4000 token limits
MAX_CONVERSATION_HISTORY = int(os.getenv('MAX_CONVERSATION_HISTORY', '100'))  # Much higher limit
MAX_TOKENS = int(os.getenv('MAX_TOKENS', '3000'))  # Increased to use your 4000 out limit
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.8'))

# Context Management - Using your full 8000 input token capacity
MAX_CONTEXT_TOKENS = int(os.getenv('MAX_CONTEXT_TOKENS', '8000'))  # Your full input limit
RESERVED_TOKENS = int(os.getenv('RESERVED_TOKENS', '500'))  # Minimal reserve for current interaction
AVAILABLE_HISTORY_TOKENS = MAX_CONTEXT_TOKENS - RESERVED_TOKENS  # 7500 tokens for conversation history

# Validation (warn rather than raise at import time)
if not TELEGRAM_TOKEN:
    warnings.warn("TELEGRAM_TOKEN is not set. The bot cannot run without it.")
if not GITHUB_TOKEN:
    warnings.warn("GITHUB_TOKEN is not set. AI responses will not work without it.") 