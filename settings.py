"""Typed application settings for LLMChatEngine."""

from __future__ import annotations

import re
import warnings
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_BOT_NAME = "Bot"
DEFAULT_PROVIDER = "azure"
DEFAULT_LMSTUDIO_MODEL = "deepseek/DeepSeek-V3-0324"
DEFAULT_MAX_CONVERSATION_HISTORY = 100
DEFAULT_MAX_TOKENS = 8000
DEFAULT_TEMPERATURE = 0.8
DEFAULT_MAX_CONTEXT_TOKENS = 8000
DEFAULT_RESERVED_TOKENS = 500
DEFAULT_BOT_PERSONALITY = (
    f"You are {DEFAULT_BOT_NAME}. Respond naturally, helpfully, and in-character according "
    "to the explicit bot configuration provided by the app. Do not assume a romantic role "
    "unless the bot configuration explicitly says so."
)
DEFAULT_PROACTIVE_PROMPT = (
    "Сгенерируй дружеское, заботливое сообщение, чтобы проверить, как у пользователя дела, "
    "на том языке, на котором ты обычно с ним разговариваешь. Сообщение должно быть кратким, "
    "естественным и прозрачным: не утверждай, что ты человек. Не повторяйся"
)
SUMMARIZATION_PROMPT = """
You are maintaining a running summary of a conversation.

Existing summary:
{existing_summary}

New conversation text:
{text}

Update the user-focused summary based on the new text, keeping it concise and only include relevant user details.
"""


class DatabaseSettings(BaseModel):
    url: str | None
    use_pgvector: bool
    password: str | None


class RedisSettings(BaseModel):
    url: str
    proactive_url: str
    message_queue_url: str


class LLMSettings(BaseModel):
    provider: str
    azure_endpoint: str | None
    azure_api_key: str | None
    azure_model: str | None
    lmstudio_model: str
    lmstudio_base_url: str
    lmstudio_auto_load: bool
    lmstudio_max_load_wait: int
    lmstudio_server_timeout: int
    lmstudio_startup_check: bool
    gemini_api_key: str | None
    gemini_model: str | None
    gemini_embedding_model: str | None


class PromptSettings(BaseModel):
    max_memory_items: int
    memory_token_budget_ratio: float
    truncation_length: int
    include_system_template: bool
    history_budget: int
    reply_token_budget: int


class MemorySettings(BaseModel):
    enabled: bool
    embedding_provider: str
    summarizer_mode: str
    embed_model: str
    embed_dim: int
    vector_store_table_name: str
    chunk_max_messages: int
    chunk_target_tokens: int
    trigger_every_n_messages: int
    retrieval_expand_neighbors: int


class CadenceSettings(BaseModel):
    name: str
    interval: int
    jitter: int

    def as_dict(self) -> dict[str, int | str]:
        return {"name": self.name, "interval": self.interval, "jitter": self.jitter}


class ProactiveSettings(BaseModel):
    enabled: bool
    redis_url: str
    cadences: list[CadenceSettings]
    quiet_hours_enabled: bool
    quiet_hours_start: str
    quiet_hours_end: str
    max_consecutive_outreaches: int
    retry_delay: int
    max_retries: int
    restart_delay_max: int
    prompt: str
    recent_history_limit: int
    recent_proactive_limit: int
    memory_hint_limit: int
    random_seed: str


class QueueSettings(BaseModel):
    redis_url: str
    max_retries: int
    lock_timeout: int
    lock_refresh_interval: int
    dispatcher_interval: float


class BooksSettings(BaseModel):
    rag_enabled: bool
    storage_dir: str
    keep_source_files: bool
    chunk_target_tokens: int
    chunk_overlap_tokens: int
    rag_top_k: int
    rag_min_score: float
    rag_token_budget_ratio: float
    rag_expand_neighbors: int
    embed_batch_size: int


class BotSettings(BaseModel):
    name: str
    personality: str
    request_timeout: float
    message_preview_length: int
    short_message_threshold: int
    polling_interval: float
    max_conversation_history: int
    temperature: float
    max_active_messages: int
    max_context_tokens: int
    reserved_tokens: int
    available_history_tokens: int


class AdminSettings(BaseModel):
    bot_token: str | None
    user_ids: list[int]
    token_encryption_key: str


class TypingSettings(BaseModel):
    min_speed: int
    max_speed: int
    max_delay: int
    random_offset_min: float
    random_offset_max: float
    indicate_during_delay: bool


class BufferSettings(BaseModel):
    short_message_timeout: float
    long_message_timeout: float
    max_messages: int
    word_count_threshold: int
    cleanup_interval: int


class AppSettings(BaseSettings):
    """Environment-backed settings with grouped accessors and compatibility fields."""

    model_config = SettingsConfigDict(extra="ignore")
    _explicit_fields: set[str] = PrivateAttr(default_factory=set)

    def __init__(self, **data: Any) -> None:
        explicit_fields = set(data)
        super().__init__(**data)
        self._explicit_fields = explicit_fields

    TELEGRAM_TOKEN: str | None = None
    ADMIN_BOT_TOKEN: str | None = None
    ADMIN_USER_IDS: list[int] = Field(default_factory=list)
    TOKEN_ENCRYPTION_KEY: str = ""

    DATABASE_URL: str | None = None
    USE_PGVECTOR: bool = True
    DB_PASSWORD: str | None = None

    PROVIDER: str = DEFAULT_PROVIDER
    AZURE_ENDPOINT: str | None = None
    AZURE_API_KEY: str | None = None
    AZURE_MODEL: str | None = None
    LMSTUDIO_MODEL: str = DEFAULT_LMSTUDIO_MODEL
    LMSTUDIO_BASE_URL: str = "http://host.docker.internal:1234/v1"
    LMSTUDIO_AUTO_LOAD: bool = True
    LMSTUDIO_MAX_LOAD_WAIT: int = 300
    LMSTUDIO_SERVER_TIMEOUT: int = 80
    LMSTUDIO_STARTUP_CHECK: bool = True
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str | None = None
    GEMINI_EMBEDDING_MODEL: str | None = None

    BOT_NAME: str = DEFAULT_BOT_NAME
    BOT_PERSONALITY: str = DEFAULT_BOT_PERSONALITY
    MAX_CONVERSATION_HISTORY: int = DEFAULT_MAX_CONVERSATION_HISTORY
    TEMPERATURE: float = DEFAULT_TEMPERATURE
    MAX_ACTIVE_MESSAGES: int = 50
    MAX_CONTEXT_TOKENS: int = Field(default=DEFAULT_MAX_CONTEXT_TOKENS, gt=0)
    RESERVED_TOKENS: int = Field(default=DEFAULT_RESERVED_TOKENS, ge=0)
    REQUEST_TIMEOUT: float = Field(default=80.0, gt=0)
    MESSAGE_PREVIEW_LENGTH: int = Field(default=50, gt=0)
    SHORT_MESSAGE_THRESHOLD: int = Field(default=10, ge=0)
    POLLING_INTERVAL: float = Field(default=0.5, gt=0)

    PROMPT_MAX_MEMORY_ITEMS: int = Field(default=3, gt=0)
    PROMPT_MEMORY_TOKEN_BUDGET_RATIO: float = Field(default=0.4, ge=0, le=1)
    PROMPT_TRUNCATION_LENGTH: int = Field(default=200, gt=0)
    PROMPT_INCLUDE_SYSTEM_TEMPLATE: bool = True
    PROMPT_HISTORY_BUDGET: int | None = Field(default=None, gt=0)
    PROMPT_REPLY_TOKEN_BUDGET: int | None = Field(default=None, gt=0)

    MEMORY_ENABLED: bool = True
    MEMORY_EMBEDDING_PROVIDER: str = "lmstudio"
    MEMORY_SUMMARIZER_MODE: str = "local"
    MEMORY_EMBED_MODEL: str = "text-embedding-qwen3-embedding-0.6b"
    MEMORY_EMBED_DIM: int = Field(default=1024, gt=0)
    VECTOR_STORE_TABLE_NAME: str = "llama_pg_vector_store"
    MEMORY_CHUNK_MAX_MESSAGES: int = Field(default=4, ge=2)
    MEMORY_CHUNK_TARGET_TOKENS: int = Field(default=300, ge=50)
    MEMORY_TRIGGER_EVERY_N_MESSAGES: int = Field(default=4, ge=2)
    MEMORY_RETRIEVAL_EXPAND_NEIGHBORS: int = Field(default=1, ge=0)

    BOOK_RAG_ENABLED: bool = True
    BOOKS_STORAGE_DIR: str = "./book_files"
    BOOKS_KEEP_SOURCE_FILES: bool = False
    BOOK_CHUNK_TARGET_TOKENS: int = Field(default=400, ge=50)
    BOOK_CHUNK_OVERLAP_TOKENS: int = Field(default=50, ge=0)
    BOOK_RAG_TOP_K: int = Field(default=4, gt=0)
    BOOK_RAG_MIN_SCORE: float = Field(default=0.35, ge=0, le=1)
    BOOK_RAG_TOKEN_BUDGET_RATIO: float = Field(default=0.25, ge=0, le=1)
    BOOK_RAG_EXPAND_NEIGHBORS: int = Field(default=1, ge=0)
    BOOK_EMBED_BATCH_SIZE: int = Field(default=64, gt=0)

    MIN_TYPING_SPEED: int = 10
    MAX_TYPING_SPEED: int = 30
    MAX_DELAY: int = 5
    RANDOM_OFFSET_MIN: float = 0.1
    RANDOM_OFFSET_MAX: float = 0.5
    INDICATE_TYPING_DURING_DELAY: bool = False

    REDIS_URL: str = "redis://redis:6379/0"
    PROACTIVE_MESSAGING_ENABLED: bool = True
    PROACTIVE_MESSAGING_REDIS_URL: str | None = None
    MESSAGE_QUEUE_REDIS_URL: str | None = None
    MESSAGE_QUEUE_MAX_RETRIES: int = Field(default=3, ge=0)
    MESSAGE_QUEUE_LOCK_TIMEOUT: int = Field(default=30, gt=0)
    MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL: int = Field(default=10, gt=0)
    MESSAGE_QUEUE_DISPATCHER_INTERVAL: float = Field(default=0.1, gt=0)

    PROACTIVE_MESSAGING_INTERVAL_1H: int = 3600
    PROACTIVE_MESSAGING_JITTER_1H: int = 20
    PROACTIVE_MESSAGING_INTERVAL_9H: int = 32400
    PROACTIVE_MESSAGING_JITTER_9H: int = 180
    PROACTIVE_MESSAGING_INTERVAL_1D: int = 86400
    PROACTIVE_MESSAGING_JITTER_1D: int = 720
    PROACTIVE_MESSAGING_INTERVAL_1W: int = 604800
    PROACTIVE_MESSAGING_JITTER_1W: int = 4320
    PROACTIVE_MESSAGING_INTERVAL_1MO: int = 2592000
    PROACTIVE_MESSAGING_JITTER_1MO: int = 8640
    PROACTIVE_MESSAGING_QUIET_HOURS_ENABLED: bool = True
    PROACTIVE_MESSAGING_QUIET_HOURS_START: str = "02:30"
    PROACTIVE_MESSAGING_QUIET_HOURS_END: str = "08:00"
    PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES: int = 5
    PROACTIVE_MESSAGING_RETRY_DELAY: int = 300
    PROACTIVE_MESSAGING_MAX_RETRIES: int = 3
    PROACTIVE_MESSAGING_RESTART_DELAY_MAX: int = 900
    PROACTIVE_MESSAGING_PROMPT: str = DEFAULT_PROACTIVE_PROMPT
    PROACTIVE_MESSAGING_RECENT_HISTORY_LIMIT: int = 8
    PROACTIVE_MESSAGING_RECENT_PROACTIVE_LIMIT: int = 6
    PROACTIVE_MESSAGING_MEMORY_HINT_LIMIT: int = 5
    PROACTIVE_MESSAGING_RANDOM_SEED: str = ""

    BUFFER_SHORT_MESSAGE_TIMEOUT: float = 4
    BUFFER_LONG_MESSAGE_TIMEOUT: float = 0.1
    BUFFER_MAX_MESSAGES: int = 8
    BUFFER_WORD_COUNT_THRESHOLD: int = 30
    BUFFER_CLEANUP_INTERVAL: int = 300

    @field_validator("ADMIN_USER_IDS", mode="before")
    @classmethod
    def _parse_admin_user_ids(cls, value: Any) -> list[int]:
        if value in (None, ""):
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate_settings(self) -> "AppSettings":
        if self.RESERVED_TOKENS >= self.MAX_CONTEXT_TOKENS:
            raise ValueError("RESERVED_TOKENS must be less than MAX_CONTEXT_TOKENS")
        if self.BOOK_CHUNK_OVERLAP_TOKENS >= self.BOOK_CHUNK_TARGET_TOKENS:
            raise ValueError("BOOK_CHUNK_OVERLAP_TOKENS must be less than BOOK_CHUNK_TARGET_TOKENS")
        if self.MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL >= self.MESSAGE_QUEUE_LOCK_TIMEOUT:
            raise ValueError("MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL must be less than MESSAGE_QUEUE_LOCK_TIMEOUT")
        if self.prompt_history_budget > self.MAX_CONTEXT_TOKENS:
            raise ValueError("PROMPT_HISTORY_BUDGET must not exceed MAX_CONTEXT_TOKENS")
        if self.prompt_reply_token_budget > self.MAX_CONTEXT_TOKENS:
            raise ValueError("PROMPT_REPLY_TOKEN_BUDGET must not exceed MAX_CONTEXT_TOKENS")
        if not self.TELEGRAM_TOKEN:
            warnings.warn("TELEGRAM_TOKEN is not set. The bot cannot run without it.")
        if not self.DATABASE_URL:
            warnings.warn("DATABASE_URL is required for PostgreSQL storage.")
        if self.PROVIDER not in {"azure", "lmstudio", "gemini"}:
            warnings.warn(
                f"PROVIDER '{self.PROVIDER}' is not supported. "
                "Supported values: 'azure', 'lmstudio', 'gemini'"
            )
        if self.PROVIDER == "azure":
            if not self.AZURE_ENDPOINT:
                warnings.warn("AZURE_ENDPOINT is not set for Azure provider")
            if not self.AZURE_API_KEY:
                warnings.warn("AZURE_API_KEY is not set for Azure provider")
            if not self.AZURE_MODEL:
                warnings.warn("AZURE_MODEL is not set for Azure provider")
        if self.PROVIDER == "lmstudio":
            if not self.LMSTUDIO_MODEL:
                warnings.warn("LMSTUDIO_MODEL is not set for LM Studio provider")
            if not self.LMSTUDIO_BASE_URL:
                warnings.warn("LMSTUDIO_BASE_URL is not set for LM Studio provider")
            if self.LMSTUDIO_MAX_LOAD_WAIT < 30:
                warnings.warn("LMSTUDIO_MAX_LOAD_WAIT is very low, model loading might timeout")
        if self.PROVIDER == "gemini":
            if not self.GEMINI_API_KEY:
                warnings.warn("GEMINI_API_KEY is not set for Gemini provider")
            if not self.GEMINI_MODEL:
                warnings.warn("GEMINI_MODEL is not set for Gemini provider")

        self._warn_between("PROMPT_MEMORY_TOKEN_BUDGET_RATIO", self.PROMPT_MEMORY_TOKEN_BUDGET_RATIO)
        self._warn_between("BOOK_RAG_MIN_SCORE", self.BOOK_RAG_MIN_SCORE)
        self._warn_between("BOOK_RAG_TOKEN_BUDGET_RATIO", self.BOOK_RAG_TOKEN_BUDGET_RATIO)

        if self.PROMPT_MAX_MEMORY_ITEMS < 1:
            warnings.warn("PROMPT_MAX_MEMORY_ITEMS should be at least 1")
        if self.prompt_history_budget > self.MAX_CONTEXT_TOKENS:
            warnings.warn("PROMPT_HISTORY_BUDGET should not exceed MAX_CONTEXT_TOKENS")
        if self.prompt_reply_token_budget > self.MAX_CONTEXT_TOKENS:
            warnings.warn("PROMPT_REPLY_TOKEN_BUDGET should not exceed MAX_CONTEXT_TOKENS")
        if self.MEMORY_ENABLED and not self.MEMORY_EMBED_MODEL:
            warnings.warn("MEMORY_ENABLED is true, but MEMORY_EMBED_MODEL is not set.")
        if self.MEMORY_ENABLED and self.MEMORY_EMBEDDING_PROVIDER not in {"lmstudio", "gemini"}:
            warnings.warn(
                f"MEMORY_EMBEDDING_PROVIDER '{self.MEMORY_EMBEDDING_PROVIDER}' is not supported. "
                "Supported values: 'lmstudio', 'gemini'"
            )
        if self.MEMORY_ENABLED and self.MEMORY_EMBEDDING_PROVIDER == "gemini" and not self.GEMINI_EMBEDDING_MODEL:
            warnings.warn("GEMINI_EMBEDDING_MODEL is required when MEMORY_EMBEDDING_PROVIDER is 'gemini'")
        if self.MEMORY_CHUNK_MAX_MESSAGES < 2:
            warnings.warn("MEMORY_CHUNK_MAX_MESSAGES should be at least 2 (one user+assistant pair)")
        if self.MEMORY_CHUNK_TARGET_TOKENS < 50:
            warnings.warn("MEMORY_CHUNK_TARGET_TOKENS seems too low, consider at least 50")
        if self.MEMORY_TRIGGER_EVERY_N_MESSAGES < 2:
            warnings.warn("MEMORY_TRIGGER_EVERY_N_MESSAGES should be at least 2")
        if self.BOOK_CHUNK_TARGET_TOKENS < 50:
            warnings.warn("BOOK_CHUNK_TARGET_TOKENS should be at least 50")
        if self.BOOK_CHUNK_OVERLAP_TOKENS < 0:
            warnings.warn("BOOK_CHUNK_OVERLAP_TOKENS should not be negative")
        if self.BOOK_CHUNK_OVERLAP_TOKENS >= self.BOOK_CHUNK_TARGET_TOKENS:
            warnings.warn("BOOK_CHUNK_OVERLAP_TOKENS should be less than BOOK_CHUNK_TARGET_TOKENS")
        if self.BOOK_RAG_TOP_K < 1:
            warnings.warn("BOOK_RAG_TOP_K should be at least 1")
        if self.BOOK_RAG_EXPAND_NEIGHBORS < 0:
            warnings.warn("BOOK_RAG_EXPAND_NEIGHBORS should not be negative")
        if self.BOOK_EMBED_BATCH_SIZE < 1:
            warnings.warn("BOOK_EMBED_BATCH_SIZE should be at least 1")
        if self.PROACTIVE_MESSAGING_ENABLED:
            self._validate_proactive()
        self._validate_buffer()
        return self

    @staticmethod
    def _warn_between(name: str, value: float) -> None:
        if value < 0 or value > 1:
            warnings.warn(f"{name} should be between 0 and 1")

    def _validate_proactive(self) -> None:
        if not self.proactive_redis_url:
            warnings.warn("PROACTIVE_MESSAGING_REDIS_URL is required when proactive messaging is enabled")
        if not self.PROACTIVE_MESSAGING_PROMPT:
            warnings.warn("PROACTIVE_MESSAGING_PROMPT should not be empty")
        time_pattern = re.compile(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
        if self.PROACTIVE_MESSAGING_QUIET_HOURS_ENABLED:
            if not time_pattern.match(self.PROACTIVE_MESSAGING_QUIET_HOURS_START):
                warnings.warn("PROACTIVE_MESSAGING_QUIET_HOURS_START should be in HH:MM format (24-hour)")
            if not time_pattern.match(self.PROACTIVE_MESSAGING_QUIET_HOURS_END):
                warnings.warn("PROACTIVE_MESSAGING_QUIET_HOURS_END should be in HH:MM format (24-hour)")
        if self.PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES <= 0:
            warnings.warn("PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES should be positive")
        if self.PROACTIVE_MESSAGING_RETRY_DELAY < 0:
            warnings.warn("PROACTIVE_MESSAGING_RETRY_DELAY should be non-negative")
        if self.PROACTIVE_MESSAGING_MAX_RETRIES < 0:
            warnings.warn("PROACTIVE_MESSAGING_MAX_RETRIES should be non-negative")
        if self.PROACTIVE_MESSAGING_RESTART_DELAY_MAX <= 31:
            warnings.warn("PROACTIVE_MESSAGING_RESTART_DELAY_MAX should be positive and >31s")

    def _validate_buffer(self) -> None:
        if self.BUFFER_SHORT_MESSAGE_TIMEOUT <= 0:
            warnings.warn("BUFFER_SHORT_MESSAGE_TIMEOUT should be positive")
        if self.BUFFER_LONG_MESSAGE_TIMEOUT <= 0:
            warnings.warn("BUFFER_LONG_MESSAGE_TIMEOUT should be positive")
        if self.BUFFER_MAX_MESSAGES <= 0:
            warnings.warn("BUFFER_MAX_MESSAGES should be positive")
        if self.BUFFER_WORD_COUNT_THRESHOLD <= 0:
            warnings.warn("BUFFER_WORD_COUNT_THRESHOLD should be positive")
        if self.BUFFER_LONG_MESSAGE_TIMEOUT >= self.BUFFER_SHORT_MESSAGE_TIMEOUT:
            warnings.warn("BUFFER_LONG_MESSAGE_TIMEOUT should be less than BUFFER_SHORT_MESSAGE_TIMEOUT for effective buffering")
        if self.BUFFER_CLEANUP_INTERVAL <= 0:
            warnings.warn("BUFFER_CLEANUP_INTERVAL should be positive")

    @property
    def available_history_tokens(self) -> int:
        return self.MAX_CONTEXT_TOKENS - self.RESERVED_TOKENS

    @property
    def prompt_history_budget(self) -> int:
        if (
            "PROMPT_HISTORY_BUDGET" not in self._explicit_fields
            and ("MAX_CONTEXT_TOKENS" in self._explicit_fields or "RESERVED_TOKENS" in self._explicit_fields)
        ):
            return self.available_history_tokens
        return self.PROMPT_HISTORY_BUDGET or self.available_history_tokens

    @property
    def prompt_reply_token_budget(self) -> int:
        if "PROMPT_REPLY_TOKEN_BUDGET" not in self._explicit_fields and "RESERVED_TOKENS" in self._explicit_fields:
            return self.RESERVED_TOKENS
        return self.PROMPT_REPLY_TOKEN_BUDGET or self.RESERVED_TOKENS

    @property
    def proactive_redis_url(self) -> str:
        if "REDIS_URL" in self._explicit_fields and "PROACTIVE_MESSAGING_REDIS_URL" not in self._explicit_fields:
            return self.REDIS_URL
        return self.PROACTIVE_MESSAGING_REDIS_URL or self.REDIS_URL

    @property
    def message_queue_redis_url(self) -> str:
        if "REDIS_URL" in self._explicit_fields and "MESSAGE_QUEUE_REDIS_URL" not in self._explicit_fields:
            return self.REDIS_URL
        return self.MESSAGE_QUEUE_REDIS_URL or self.REDIS_URL

    @property
    def proactive_cadences(self) -> list[CadenceSettings]:
        return [
            CadenceSettings(name="1h", interval=self.PROACTIVE_MESSAGING_INTERVAL_1H, jitter=self.PROACTIVE_MESSAGING_JITTER_1H),
            CadenceSettings(name="9h", interval=self.PROACTIVE_MESSAGING_INTERVAL_9H, jitter=self.PROACTIVE_MESSAGING_JITTER_9H),
            CadenceSettings(name="1d", interval=self.PROACTIVE_MESSAGING_INTERVAL_1D, jitter=self.PROACTIVE_MESSAGING_JITTER_1D),
            CadenceSettings(name="1w", interval=self.PROACTIVE_MESSAGING_INTERVAL_1W, jitter=self.PROACTIVE_MESSAGING_JITTER_1W),
            CadenceSettings(name="1mo", interval=self.PROACTIVE_MESSAGING_INTERVAL_1MO, jitter=self.PROACTIVE_MESSAGING_JITTER_1MO),
        ]

    @property
    def db(self) -> DatabaseSettings:
        return DatabaseSettings(url=self.DATABASE_URL, use_pgvector=self.USE_PGVECTOR, password=self.DB_PASSWORD)

    @property
    def redis(self) -> RedisSettings:
        return RedisSettings(url=self.REDIS_URL, proactive_url=self.proactive_redis_url, message_queue_url=self.message_queue_redis_url)

    @property
    def llm(self) -> LLMSettings:
        return LLMSettings(
            provider=self.PROVIDER,
            azure_endpoint=self.AZURE_ENDPOINT,
            azure_api_key=self.AZURE_API_KEY,
            azure_model=self.AZURE_MODEL,
            lmstudio_model=self.LMSTUDIO_MODEL,
            lmstudio_base_url=self.LMSTUDIO_BASE_URL,
            lmstudio_auto_load=self.LMSTUDIO_AUTO_LOAD,
            lmstudio_max_load_wait=self.LMSTUDIO_MAX_LOAD_WAIT,
            lmstudio_server_timeout=self.LMSTUDIO_SERVER_TIMEOUT,
            lmstudio_startup_check=self.LMSTUDIO_STARTUP_CHECK,
            gemini_api_key=self.GEMINI_API_KEY,
            gemini_model=self.GEMINI_MODEL,
            gemini_embedding_model=self.GEMINI_EMBEDDING_MODEL,
        )

    @property
    def prompts(self) -> PromptSettings:
        return PromptSettings(
            max_memory_items=self.PROMPT_MAX_MEMORY_ITEMS,
            memory_token_budget_ratio=self.PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
            truncation_length=self.PROMPT_TRUNCATION_LENGTH,
            include_system_template=self.PROMPT_INCLUDE_SYSTEM_TEMPLATE,
            history_budget=self.prompt_history_budget,
            reply_token_budget=self.prompt_reply_token_budget,
        )

    @property
    def memory(self) -> MemorySettings:
        return MemorySettings(
            enabled=self.MEMORY_ENABLED,
            embedding_provider=self.MEMORY_EMBEDDING_PROVIDER,
            summarizer_mode=self.MEMORY_SUMMARIZER_MODE,
            embed_model=self.MEMORY_EMBED_MODEL,
            embed_dim=self.MEMORY_EMBED_DIM,
            vector_store_table_name=self.VECTOR_STORE_TABLE_NAME,
            chunk_max_messages=self.MEMORY_CHUNK_MAX_MESSAGES,
            chunk_target_tokens=self.MEMORY_CHUNK_TARGET_TOKENS,
            trigger_every_n_messages=self.MEMORY_TRIGGER_EVERY_N_MESSAGES,
            retrieval_expand_neighbors=self.MEMORY_RETRIEVAL_EXPAND_NEIGHBORS,
        )

    @property
    def proactive(self) -> ProactiveSettings:
        return ProactiveSettings(
            enabled=self.PROACTIVE_MESSAGING_ENABLED,
            redis_url=self.proactive_redis_url,
            cadences=self.proactive_cadences,
            quiet_hours_enabled=self.PROACTIVE_MESSAGING_QUIET_HOURS_ENABLED,
            quiet_hours_start=self.PROACTIVE_MESSAGING_QUIET_HOURS_START,
            quiet_hours_end=self.PROACTIVE_MESSAGING_QUIET_HOURS_END,
            max_consecutive_outreaches=self.PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES,
            retry_delay=self.PROACTIVE_MESSAGING_RETRY_DELAY,
            max_retries=self.PROACTIVE_MESSAGING_MAX_RETRIES,
            restart_delay_max=self.PROACTIVE_MESSAGING_RESTART_DELAY_MAX,
            prompt=self.PROACTIVE_MESSAGING_PROMPT,
            recent_history_limit=self.PROACTIVE_MESSAGING_RECENT_HISTORY_LIMIT,
            recent_proactive_limit=self.PROACTIVE_MESSAGING_RECENT_PROACTIVE_LIMIT,
            memory_hint_limit=self.PROACTIVE_MESSAGING_MEMORY_HINT_LIMIT,
            random_seed=self.PROACTIVE_MESSAGING_RANDOM_SEED,
        )

    @property
    def queue(self) -> QueueSettings:
        return QueueSettings(
            redis_url=self.message_queue_redis_url,
            max_retries=self.MESSAGE_QUEUE_MAX_RETRIES,
            lock_timeout=self.MESSAGE_QUEUE_LOCK_TIMEOUT,
            lock_refresh_interval=self.MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL,
            dispatcher_interval=self.MESSAGE_QUEUE_DISPATCHER_INTERVAL,
        )

    @property
    def books(self) -> BooksSettings:
        return BooksSettings(
            rag_enabled=self.BOOK_RAG_ENABLED,
            storage_dir=self.BOOKS_STORAGE_DIR,
            keep_source_files=self.BOOKS_KEEP_SOURCE_FILES,
            chunk_target_tokens=self.BOOK_CHUNK_TARGET_TOKENS,
            chunk_overlap_tokens=self.BOOK_CHUNK_OVERLAP_TOKENS,
            rag_top_k=self.BOOK_RAG_TOP_K,
            rag_min_score=self.BOOK_RAG_MIN_SCORE,
            rag_token_budget_ratio=self.BOOK_RAG_TOKEN_BUDGET_RATIO,
            rag_expand_neighbors=self.BOOK_RAG_EXPAND_NEIGHBORS,
            embed_batch_size=self.BOOK_EMBED_BATCH_SIZE,
        )

    @property
    def bot(self) -> BotSettings:
        return BotSettings(
            name=self.BOT_NAME,
            personality=self.BOT_PERSONALITY,
            request_timeout=self.REQUEST_TIMEOUT,
            message_preview_length=self.MESSAGE_PREVIEW_LENGTH,
            short_message_threshold=self.SHORT_MESSAGE_THRESHOLD,
            polling_interval=self.POLLING_INTERVAL,
            max_conversation_history=self.MAX_CONVERSATION_HISTORY,
            temperature=self.TEMPERATURE,
            max_active_messages=self.MAX_ACTIVE_MESSAGES,
            max_context_tokens=self.MAX_CONTEXT_TOKENS,
            reserved_tokens=self.RESERVED_TOKENS,
            available_history_tokens=self.available_history_tokens,
        )

    @property
    def admin(self) -> AdminSettings:
        return AdminSettings(
            bot_token=self.ADMIN_BOT_TOKEN,
            user_ids=self.ADMIN_USER_IDS,
            token_encryption_key=self.TOKEN_ENCRYPTION_KEY,
        )

    @property
    def typing(self) -> TypingSettings:
        return TypingSettings(
            min_speed=self.MIN_TYPING_SPEED,
            max_speed=self.MAX_TYPING_SPEED,
            max_delay=self.MAX_DELAY,
            random_offset_min=self.RANDOM_OFFSET_MIN,
            random_offset_max=self.RANDOM_OFFSET_MAX,
            indicate_during_delay=self.INDICATE_TYPING_DURING_DELAY,
        )

    @property
    def buffer(self) -> BufferSettings:
        return BufferSettings(
            short_message_timeout=self.BUFFER_SHORT_MESSAGE_TIMEOUT,
            long_message_timeout=self.BUFFER_LONG_MESSAGE_TIMEOUT,
            max_messages=self.BUFFER_MAX_MESSAGES,
            word_count_threshold=self.BUFFER_WORD_COUNT_THRESHOLD,
            cleanup_interval=self.BUFFER_CLEANUP_INTERVAL,
        )


def build_settings() -> AppSettings:
    """Build settings from the current environment."""
    return AppSettings()


settings = build_settings()
