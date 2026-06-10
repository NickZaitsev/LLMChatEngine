"""Factory for configured memory embedding models."""

import logging

from core.abstractions import EmbeddingModel
from settings import AppSettings, build_settings

logger = logging.getLogger(__name__)


def build_embedding_model(settings: AppSettings | None = None) -> EmbeddingModel:
    """Build the configured embedding model."""
    app_settings = settings or build_settings()
    memory_settings = app_settings.memory
    llm_settings = app_settings.llm

    if memory_settings.embedding_provider == "gemini":
        from memory.llamaindex.gemini import GeminiEmbeddingModel

        logger.info("Using Gemini embedding model: %s", llm_settings.gemini_embedding_model)
        return GeminiEmbeddingModel(model_name=llm_settings.gemini_embedding_model)

    if memory_settings.embedding_provider == "lmstudio":
        from memory.llamaindex.embedding import LMStudioEmbeddingModel

        logger.info("Using LMStudio embedding model: %s", memory_settings.embed_model)
        return LMStudioEmbeddingModel(memory_settings.embed_model)

    raise ValueError(f"Unsupported embedding provider: {memory_settings.embedding_provider}")
