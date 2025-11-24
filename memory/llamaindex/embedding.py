"""
LlamaIndex embedding model implementations.
"""
import logging
from typing import List
from llama_index.embeddings.openai import OpenAIEmbedding
from core.abstractions import EmbeddingModel as EmbeddingModelAbstraction
import config

logger = logging.getLogger(__name__)


class LMStudioEmbeddingModel(EmbeddingModelAbstraction):
    """
    LMStudioEmbeddingModel implementation for LlamaIndex.
    Uses a local LMStudio model.
    """

    def __init__(self, model_name: str):
        """
        Initialize the LMStudioEmbeddingModel.

        Args:
            model_path: The path to a local LMStudio model directory.
        """
        logger.info(f"Loading local LMStudio model {model_name}...")
        self._model = OpenAIEmbedding(
            api_key="whatever-is-in-lmstudio",
            api_base=config.LMSTUDIO_BASE_URL.rstrip("/"),
            model_name=model_name,
        )

        if config.LMSTUDIO_AUTO_LOAD:
            self._warm_up()

    def _warm_up(self):
        """Synchronously warms up the embedding model."""
        logger.info("Warming up the embedding model...")
        try:
            # Run a test embedding to warm up the model
            embedding = self._model.get_text_embedding("test")
            if embedding:
                logger.info("Embedding model warmed up successfully.")
            else:
                logger.warning("Warm-up embedding returned no result.")
        except Exception as e:
            logger.error(f"Failed to warm up embedding model: {e}", exc_info=True)

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get the embedding for a single piece of text.
        """
        try:
            # Await the async call from the underlying model
            return await self._model.aget_text_embedding(text)
        except ValueError as e:
            logger.error(f"Failed to get embedding: {e}", exc_info=True)
            return []

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get the embeddings for a list of texts.
        """
        # Await the async call from the underlying model
        return await self._model.aget_text_embedding_batch(texts)