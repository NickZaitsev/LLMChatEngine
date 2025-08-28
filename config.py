import os
import re
import warnings
from dotenv import load_dotenv

# Constants
DEFAULT_BOT_NAME = 'Luna'
DEFAULT_PROVIDER = 'azure'
DEFAULT_LMSTUDIO_MODEL = 'deepseek/DeepSeek-V3-0324'
DEFAULT_MAX_CONVERSATION_HISTORY = 100
DEFAULT_MAX_TOKENS = 8000
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
# Proactive Messaging Configuration
PROACTIVE_MESSAGING_ENABLED = os.getenv('PROACTIVE_MESSAGING_ENABLED', 'true').lower() in ('true', '1', 'yes', 'on')
PROACTIVE_MESSAGING_REDIS_URL = os.getenv('PROACTIVE_MESSAGING_REDIS_URL', 'redis://redis:6379/0')

# Proactive messaging intervals (in seconds)
PROACTIVE_MESSAGING_INTERVAL_1H = int(os.getenv('PROACTIVE_MESSAGING_INTERVAL_1H', '3600'))  # 1 hour
PROACTIVE_MESSAGING_INTERVAL_9H = int(os.getenv('PROACTIVE_MESSAGING_INTERVAL_9H', '32400'))  # 9 hours
PROACTIVE_MESSAGING_INTERVAL_1D = int(os.getenv('PROACTIVE_MESSAGING_INTERVAL_1D', '86400'))  # 1 day
PROACTIVE_MESSAGING_INTERVAL_1W = int(os.getenv('PROACTIVE_MESSAGING_INTERVAL_1W', '604800'))  # 1 week
PROACTIVE_MESSAGING_INTERVAL_1MO = int(os.getenv('PROACTIVE_MESSAGING_INTERVAL_1MO', '2592000'))  # 1 month

# Jitter for intervals (in seconds)
PROACTIVE_MESSAGING_JITTER_1H = int(os.getenv('PROACTIVE_MESSAGING_JITTER_1H', '900'))  # 15 minutes
PROACTIVE_MESSAGING_JITTER_9H = int(os.getenv('PROACTIVE_MESSAGING_JITTER_9H', '1800'))  # 30 minutes
PROACTIVE_MESSAGING_JITTER_1D = int(os.getenv('PROACTIVE_MESSAGING_JITTER_1D', '7200'))  # 2 hours
PROACTIVE_MESSAGING_JITTER_1W = int(os.getenv('PROACTIVE_MESSAGING_JITTER_1W', '43200'))  # 12 hours
PROACTIVE_MESSAGING_JITTER_1MO = int(os.getenv('PROACTIVE_MESSAGING_JITTER_1MO', '86400'))  # 1 day

# Quiet hours (in 24-hour format)
PROACTIVE_MESSAGING_QUIET_HOURS_START = os.getenv('PROACTIVE_MESSAGING_QUIET_HOURS_START', '02:30')
PROACTIVE_MESSAGING_QUIET_HOURS_END = os.getenv('PROACTIVE_MESSAGING_QUIET_HOURS_END', '08:00')

# Consecutive outreach settings
PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES = int(os.getenv('PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES', '5'))

# Retry policies
PROACTIVE_MESSAGING_RETRY_DELAY = int(os.getenv('PROACTIVE_MESSAGING_RETRY_DELAY', '300'))  # 5 minutes
PROACTIVE_MESSAGING_MAX_RETRIES = int(os.getenv('PROACTIVE_MESSAGING_MAX_RETRIES', '3'))

# Rescheduling delay for proactive messaging restart (in seconds)
PROACTIVE_MESSAGING_RESTART_DELAY_MAX = int(os.getenv('PROACTIVE_MESSAGING_RESTART_DELAY_MAX', '900'))  # 5 minutes

# Proactive message prompt
PROACTIVE_MESSAGING_PROMPT = os.getenv('PROACTIVE_MESSAGING_PROMPT', (
    "Сгенерируй дружеское, заботливое сообщение, чтобы проверить, как у пользователя дела, на том языке, на котором ты обычно с ним разговариваешь. "
    "Помни: ты человек, а не ИИ. Сообщение должно быть кратким и естественным. "
))

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
# Proactive Messaging validation
    if PROACTIVE_MESSAGING_ENABLED:
        if not PROACTIVE_MESSAGING_REDIS_URL:
            warnings.warn("PROACTIVE_MESSAGING_REDIS_URL is required when proactive messaging is enabled")
        
        # Validate intervals are positive
        intervals = [
            ("PROACTIVE_MESSAGING_INTERVAL_1H", PROACTIVE_MESSAGING_INTERVAL_1H),
            ("PROACTIVE_MESSAGING_INTERVAL_9H", PROACTIVE_MESSAGING_INTERVAL_9H),
            ("PROACTIVE_MESSAGING_INTERVAL_1D", PROACTIVE_MESSAGING_INTERVAL_1D),
            ("PROACTIVE_MESSAGING_INTERVAL_1W", PROACTIVE_MESSAGING_INTERVAL_1W),
            ("PROACTIVE_MESSAGING_INTERVAL_1MO", PROACTIVE_MESSAGING_INTERVAL_1MO)
        ]
        
        for name, value in intervals:
            if value <= 0:
                warnings.warn(f"{name} should be positive")
        
        # Validate jitter values are non-negative
        jitter_values = [
            ("PROACTIVE_MESSAGING_JITTER_1H", PROACTIVE_MESSAGING_JITTER_1H),
            ("PROACTIVE_MESSAGING_JITTER_9H", PROACTIVE_MESSAGING_JITTER_9H),
            ("PROACTIVE_MESSAGING_JITTER_1D", PROACTIVE_MESSAGING_JITTER_1D),
            ("PROACTIVE_MESSAGING_JITTER_1W", PROACTIVE_MESSAGING_JITTER_1W),
            ("PROACTIVE_MESSAGING_JITTER_1MO", PROACTIVE_MESSAGING_JITTER_1MO)
        ]
        
        for name, value in jitter_values:
            if value < 0:
                warnings.warn(f"{name} should be non-negative")
        
        # Validate quiet hours format
        time_pattern = re.compile(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
        if not time_pattern.match(PROACTIVE_MESSAGING_QUIET_HOURS_START):
            warnings.warn("PROACTIVE_MESSAGING_QUIET_HOURS_START should be in HH:MM format (24-hour)")
        if not time_pattern.match(PROACTIVE_MESSAGING_QUIET_HOURS_END):
            warnings.warn("PROACTIVE_MESSAGING_QUIET_HOURS_END should be in HH:MM format (24-hour)")
        
        # Validate consecutive outreach limit
        if PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES <= 0:
            warnings.warn("PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES should be positive")
        
        # Validate retry settings
        if PROACTIVE_MESSAGING_RETRY_DELAY < 0:
            warnings.warn("PROACTIVE_MESSAGING_RETRY_DELAY should be non-negative")
        if PROACTIVE_MESSAGING_MAX_RETRIES < 0:
            warnings.warn("PROACTIVE_MESSAGING_MAX_RETRIES should be non-negative")
        
        # Validate rescheduling delay
        if PROACTIVE_MESSAGING_RESTART_DELAY_MAX <= 31:
            warnings.warn("PROACTIVE_MESSAGING_RESTART_DELAY_MAX should be positive and >31s" )
        
        # Validate proactive messaging prompt
        if not PROACTIVE_MESSAGING_PROMPT:
            warnings.warn("PROACTIVE_MESSAGING_PROMPT should not be empty")

# Perform validation
_validate_config()