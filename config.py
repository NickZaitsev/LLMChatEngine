"""Compatibility shim for typed application settings.

New code should prefer importing AppSettings/build_settings from settings.py.
Existing modules can keep importing these module-level names during migration.
"""

import dotenv

from settings import (
    AppSettings,
    DEFAULT_BOT_NAME,
    DEFAULT_BOT_PERSONALITY,
    DEFAULT_LMSTUDIO_MODEL,
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_MAX_CONVERSATION_HISTORY,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROVIDER,
    DEFAULT_RESERVED_TOKENS,
    DEFAULT_TEMPERATURE,
    SUMMARIZATION_PROMPT,
    build_settings,
)

dotenv.load_dotenv()
settings = build_settings()

TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
ADMIN_BOT_TOKEN = settings.admin.bot_token
ADMIN_USER_IDS = settings.admin.user_ids
TOKEN_ENCRYPTION_KEY = settings.admin.token_encryption_key

DATABASE_URL = settings.db.url
USE_PGVECTOR = settings.db.use_pgvector
DB_PASSWORD = settings.db.password

PROVIDER = settings.llm.provider
AZURE_ENDPOINT = settings.llm.azure_endpoint
AZURE_API_KEY = settings.llm.azure_api_key
AZURE_MODEL = settings.llm.azure_model
LMSTUDIO_MODEL = settings.llm.lmstudio_model
LMSTUDIO_BASE_URL = settings.llm.lmstudio_base_url
LMSTUDIO_AUTO_LOAD = settings.llm.lmstudio_auto_load
LMSTUDIO_MAX_LOAD_WAIT = settings.llm.lmstudio_max_load_wait
LMSTUDIO_SERVER_TIMEOUT = settings.llm.lmstudio_server_timeout
LMSTUDIO_STARTUP_CHECK = settings.llm.lmstudio_startup_check
GEMINI_API_KEY = settings.llm.gemini_api_key
GEMINI_MODEL = settings.llm.gemini_model
GEMINI_EMBEDDING_MODEL = settings.llm.gemini_embedding_model

BOT_NAME = settings.bot.name
BOT_PERSONALITY = settings.bot.personality
MAX_CONVERSATION_HISTORY = settings.bot.max_conversation_history
TEMPERATURE = settings.bot.temperature
MAX_ACTIVE_MESSAGES = settings.bot.max_active_messages
MAX_CONTEXT_TOKENS = settings.bot.max_context_tokens
RESERVED_TOKENS = settings.bot.reserved_tokens
AVAILABLE_HISTORY_TOKENS = settings.bot.available_history_tokens
REQUEST_TIMEOUT = settings.bot.request_timeout
MESSAGE_PREVIEW_LENGTH = settings.bot.message_preview_length
SHORT_MESSAGE_THRESHOLD = settings.bot.short_message_threshold
POLLING_INTERVAL = settings.bot.polling_interval

PROMPT_MAX_MEMORY_ITEMS = settings.prompts.max_memory_items
PROMPT_MEMORY_TOKEN_BUDGET_RATIO = settings.prompts.memory_token_budget_ratio
PROMPT_TRUNCATION_LENGTH = settings.prompts.truncation_length
PROMPT_INCLUDE_SYSTEM_TEMPLATE = settings.prompts.include_system_template
PROMPT_HISTORY_BUDGET = settings.prompts.history_budget
PROMPT_REPLY_TOKEN_BUDGET = settings.prompts.reply_token_budget

MEMORY_ENABLED = settings.memory.enabled
MEMORY_EMBEDDING_PROVIDER = settings.memory.embedding_provider
MEMORY_SUMMARIZER_MODE = settings.memory.summarizer_mode
MEMORY_EMBED_MODEL = settings.memory.embed_model
MEMORY_EMBED_DIM = settings.memory.embed_dim
VECTOR_STORE_TABLE_NAME = settings.memory.vector_store_table_name
MEMORY_CHUNK_MAX_MESSAGES = settings.memory.chunk_max_messages
MEMORY_CHUNK_TARGET_TOKENS = settings.memory.chunk_target_tokens
MEMORY_TRIGGER_EVERY_N_MESSAGES = settings.memory.trigger_every_n_messages
MEMORY_RETRIEVAL_EXPAND_NEIGHBORS = settings.memory.retrieval_expand_neighbors

BOOK_RAG_ENABLED = settings.books.rag_enabled
BOOKS_STORAGE_DIR = settings.books.storage_dir
BOOKS_KEEP_SOURCE_FILES = settings.books.keep_source_files
BOOK_CHUNK_TARGET_TOKENS = settings.books.chunk_target_tokens
BOOK_CHUNK_OVERLAP_TOKENS = settings.books.chunk_overlap_tokens
BOOK_RAG_TOP_K = settings.books.rag_top_k
BOOK_RAG_MIN_SCORE = settings.books.rag_min_score
BOOK_RAG_TOKEN_BUDGET_RATIO = settings.books.rag_token_budget_ratio
BOOK_RAG_EXPAND_NEIGHBORS = settings.books.rag_expand_neighbors
BOOK_EMBED_BATCH_SIZE = settings.books.embed_batch_size

MIN_TYPING_SPEED = settings.typing.min_speed
MAX_TYPING_SPEED = settings.typing.max_speed
MAX_DELAY = settings.typing.max_delay
RANDOM_OFFSET_MIN = settings.typing.random_offset_min
RANDOM_OFFSET_MAX = settings.typing.random_offset_max
INDICATE_TYPING_DURING_DELAY = settings.typing.indicate_during_delay

REDIS_URL = settings.redis.url
PROACTIVE_MESSAGING_ENABLED = settings.proactive.enabled
PROACTIVE_MESSAGING_REDIS_URL = settings.proactive.redis_url
PROACTIVE_MESSAGING_CADENCES = [cadence.as_dict() for cadence in settings.proactive.cadences]
PROACTIVE_MESSAGING_QUIET_HOURS_ENABLED = settings.proactive.quiet_hours_enabled
PROACTIVE_MESSAGING_QUIET_HOURS_START = settings.proactive.quiet_hours_start
PROACTIVE_MESSAGING_QUIET_HOURS_END = settings.proactive.quiet_hours_end
PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES = settings.proactive.max_consecutive_outreaches
PROACTIVE_MESSAGING_RETRY_DELAY = settings.proactive.retry_delay
PROACTIVE_MESSAGING_MAX_RETRIES = settings.proactive.max_retries
PROACTIVE_MESSAGING_RESTART_DELAY_MAX = settings.proactive.restart_delay_max
PROACTIVE_MESSAGING_PROMPT = settings.proactive.prompt
PROACTIVE_MESSAGING_RECENT_HISTORY_LIMIT = settings.proactive.recent_history_limit
PROACTIVE_MESSAGING_RECENT_PROACTIVE_LIMIT = settings.proactive.recent_proactive_limit
PROACTIVE_MESSAGING_MEMORY_HINT_LIMIT = settings.proactive.memory_hint_limit
PROACTIVE_MESSAGING_RANDOM_SEED = settings.proactive.random_seed

MESSAGE_QUEUE_REDIS_URL = settings.queue.redis_url
MESSAGE_QUEUE_MAX_RETRIES = settings.queue.max_retries
MESSAGE_QUEUE_LOCK_TIMEOUT = settings.queue.lock_timeout
MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL = settings.queue.lock_refresh_interval
MESSAGE_QUEUE_DISPATCHER_INTERVAL = settings.queue.dispatcher_interval

BUFFER_SHORT_MESSAGE_TIMEOUT = settings.buffer.short_message_timeout
BUFFER_LONG_MESSAGE_TIMEOUT = settings.buffer.long_message_timeout
BUFFER_MAX_MESSAGES = settings.buffer.max_messages
BUFFER_WORD_COUNT_THRESHOLD = settings.buffer.word_count_threshold
BUFFER_CLEANUP_INTERVAL = settings.buffer.cleanup_interval
