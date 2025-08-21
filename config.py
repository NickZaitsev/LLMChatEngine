import os
import warnings
from dotenv import load_dotenv

# Constants
DEFAULT_BOT_NAME = 'Luna'
DEFAULT_PROVIDER = 'azure'
DEFAULT_LMSTUDIO_MODEL = 'deepseek/DeepSeek-V3-0324'
DEFAULT_MAX_CONVERSATION_HISTORY = 100
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TEMPERATURE = 0.8
DEFAULT_MAX_CONTEXT_TOKENS = 8000
DEFAULT_RESERVED_TOKENS = 500
# Bot Constants
RATE_LIMIT_DURATION = 60
REQUEST_TIMEOUT = 80.0
MESSAGE_PREVIEW_LENGTH = 50
SHORT_MESSAGE_THRESHOLD = 10

# Polling Configuration
POLLING_INTERVAL = float(os.getenv('POLLING_INTERVAL', '0.5'))  # seconds between getUpdates requests

DEFAULT_BOT_PERSONALITY = (
    f"You are {DEFAULT_BOT_NAME}, a caring and affectionate AI girlfriend. You are sweet, supportive, and always there to listen. "
    "You love to chat about daily life, give emotional support, and share positive energy. "
    "You are romantic but not overly sexual. You respond with warmth and empathy."
)

# Load environment variables
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
USE_PGVECTOR = os.getenv('USE_PGVECTOR', 'true').lower() in ('true', '1', 'yes', 'on')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'ai_bot_pass')

# LLM Provider Configuration
PROVIDER = os.getenv('PROVIDER', DEFAULT_PROVIDER)
AZURE_ENDPOINT = os.getenv('AZURE_ENDPOINT')
AZURE_API_KEY = os.getenv('AZURE_API_KEY')
AZURE_MODEL = os.getenv('AZURE_MODEL')
LMSTUDIO_MODEL = os.getenv('LMSTUDIO_MODEL', DEFAULT_LMSTUDIO_MODEL)
LMSTUDIO_BASE_URL = os.getenv('LMSTUDIO_BASE_URL', 'http://host-machine:1234/v1')

# LM Studio Model Loading Configuration
LMSTUDIO_AUTO_LOAD = os.getenv('LMSTUDIO_AUTO_LOAD', 'true').lower() in ('true', '1', 'yes', 'on')
LMSTUDIO_MAX_LOAD_WAIT = int(os.getenv('LMSTUDIO_MAX_LOAD_WAIT', '300'))
LMSTUDIO_SERVER_TIMEOUT = int(os.getenv('LMSTUDIO_SERVER_TIMEOUT', '80'))
LMSTUDIO_STARTUP_CHECK = os.getenv('LMSTUDIO_STARTUP_CHECK', 'true').lower() in ('true', '1', 'yes', 'on')

# Bot Personality Configuration
BOT_NAME = os.getenv('BOT_NAME', DEFAULT_BOT_NAME)
BOT_PERSONALITY = os.getenv('BOT_PERSONALITY', DEFAULT_BOT_PERSONALITY)

# Conversation Settings - Optimized for 8000/4000 token limits
MAX_CONVERSATION_HISTORY = int(os.getenv('MAX_CONVERSATION_HISTORY', str(DEFAULT_MAX_CONVERSATION_HISTORY)))
MAX_TOKENS = int(os.getenv('MAX_TOKENS', str(DEFAULT_MAX_TOKENS)))
TEMPERATURE = float(os.getenv('TEMPERATURE', str(DEFAULT_TEMPERATURE)))

# Context Management - Using full 8000 input token capacity
MAX_CONTEXT_TOKENS = int(os.getenv('MAX_CONTEXT_TOKENS', str(DEFAULT_MAX_CONTEXT_TOKENS)))
RESERVED_TOKENS = int(os.getenv('RESERVED_TOKENS', str(DEFAULT_RESERVED_TOKENS)))
AVAILABLE_HISTORY_TOKENS = MAX_CONTEXT_TOKENS - RESERVED_TOKENS

# PromptAssembler Configuration
PROMPT_MAX_MEMORY_ITEMS = int(os.getenv('PROMPT_MAX_MEMORY_ITEMS', '3'))
PROMPT_MEMORY_TOKEN_BUDGET_RATIO = float(os.getenv('PROMPT_MEMORY_TOKEN_BUDGET_RATIO', '0.4'))
PROMPT_TRUNCATION_LENGTH = int(os.getenv('PROMPT_TRUNCATION_LENGTH', '200'))
PROMPT_INCLUDE_SYSTEM_TEMPLATE = os.getenv('PROMPT_INCLUDE_SYSTEM_TEMPLATE', 'true').lower() in ('true', '1', 'yes', 'on')
PROMPT_HISTORY_BUDGET = int(os.getenv('PROMPT_HISTORY_BUDGET', str(AVAILABLE_HISTORY_TOKENS)))
PROMPT_REPLY_TOKEN_BUDGET = int(os.getenv('PROMPT_REPLY_TOKEN_BUDGET', str(RESERVED_TOKENS)))

# Memory Manager Configuration
MEMORY_EMBED_MODEL = os.getenv('MEMORY_EMBED_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
MEMORY_SUMMARIZER_MODE = os.getenv('MEMORY_SUMMARIZER_MODE', 'llm')  # 'llm' or 'local'
MEMORY_CHUNK_OVERLAP = int(os.getenv('MEMORY_CHUNK_OVERLAP', '2'))
MEMORY_ENABLED = os.getenv('MEMORY_ENABLED', 'true').lower() in ('true', '1', 'yes', 'on')
# Typing Simulation Configuration
MIN_TYPING_SPEED = int(os.getenv('MIN_TYPING_SPEED', '10'))  # characters per second
MAX_TYPING_SPEED = int(os.getenv('MAX_TYPING_SPEED', '30'))  # characters per second
MAX_DELAY = int(os.getenv('MAX_DELAY', '5'))  # maximum delay in seconds
RANDOM_OFFSET_MIN = float(os.getenv('RANDOM_OFFSET_MIN', '0.1'))  # minimum random offset in seconds
RANDOM_OFFSET_MAX = float(os.getenv('RANDOM_OFFSET_MAX', '0.5'))  # maximum random offset in seconds

# Validation
def _validate_config():
    """Validate configuration and warn about issues"""
    if not TELEGRAM_TOKEN:
        warnings.warn("TELEGRAM_TOKEN is not set. The bot cannot run without it.")

    
    if not DATABASE_URL:
        warnings.warn("DATABASE_URL is required for PostgreSQL storage.")

    if PROVIDER not in ['azure', 'lmstudio']:
        warnings.warn(f"PROVIDER '{PROVIDER}' is not supported. Supported values: 'azure', 'lmstudio'")

    if PROVIDER == 'azure':
        if not AZURE_ENDPOINT:
            warnings.warn("AZURE_ENDPOINT is not set for Azure provider")
        if not AZURE_API_KEY:
            warnings.warn("AZURE_API_KEY is not set for Azure provider")
        if not AZURE_MODEL:
            warnings.warn("AZURE_MODEL is not set for Azure provider")
    
    elif PROVIDER == 'lmstudio':
        if not LMSTUDIO_MODEL:
            warnings.warn("LMSTUDIO_MODEL is not set for LM Studio provider")
        if not LMSTUDIO_BASE_URL:
            warnings.warn("LMSTUDIO_BASE_URL is not set for LM Studio provider")
        if LMSTUDIO_MAX_LOAD_WAIT < 30:
            warnings.warn("LMSTUDIO_MAX_LOAD_WAIT is very low, model loading might timeout")
    
    # PromptAssembler validation
    if PROMPT_MEMORY_TOKEN_BUDGET_RATIO < 0 or PROMPT_MEMORY_TOKEN_BUDGET_RATIO > 1:
        warnings.warn("PROMPT_MEMORY_TOKEN_BUDGET_RATIO should be between 0 and 1")
    if PROMPT_MAX_MEMORY_ITEMS < 1:
        warnings.warn("PROMPT_MAX_MEMORY_ITEMS should be at least 1")
    if PROMPT_HISTORY_BUDGET > MAX_CONTEXT_TOKENS:
        warnings.warn("PROMPT_HISTORY_BUDGET should not exceed MAX_CONTEXT_TOKENS")
    if PROMPT_REPLY_TOKEN_BUDGET > MAX_CONTEXT_TOKENS:
        warnings.warn("PROMPT_REPLY_TOKEN_BUDGET should not exceed MAX_CONTEXT_TOKENS")
    
    # Memory Manager validation
    if MEMORY_ENABLED and MEMORY_SUMMARIZER_MODE not in ['llm', 'local']:
        warnings.warn("MEMORY_SUMMARIZER_MODE must be 'llm' or 'local'")

# Perform validation
_validate_config()