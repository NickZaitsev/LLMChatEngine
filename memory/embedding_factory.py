"""Factory for configured memory embedding models."""

import logging

from core.abstractions import EmbeddingModel

logger = logging.getLogger(__name__)


def build_embedding_model() -> EmbeddingModel:
    """Build the configured embedding model."""
    from config import (
        MEMORY_EMBEDDING_PROVIDER,
        MEMORY_EMBED_MODEL,
        GEMINI_EMBEDDING_MODEL,
    )

    if MEMORY_EMBEDDING_PROVIDER == "gemini":
        from memory.llamaindex.gemini import GeminiEmbeddingModel

        logger.info("Using Gemini embedding model: %s", GEMINI_EMBEDDING_MODEL)
        return GeminiEmbeddingModel(model_name=GEMINI_EMBEDDING_MODEL)

    if MEMORY_EMBEDDING_PROVIDER == "lmstudio":
        from memory.llamaindex.embedding import LMStudioEmbeddingModel

        logger.info("Using LMStudio embedding model: %s", MEMORY_EMBED_MODEL)
        return LMStudioEmbeddingModel(MEMORY_EMBED_MODEL)

    raise ValueError(f"Unsupported embedding provider: {MEMORY_EMBEDDING_PROVIDER}")
