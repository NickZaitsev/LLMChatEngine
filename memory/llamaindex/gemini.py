"""
LlamaIndex embedding model implementation for Gemini.
"""
import logging
from typing import List

from llama_index.embeddings.gemini import GeminiEmbedding

import config
from core.abstractions import EmbeddingModel as EmbeddingModelAbstraction

logger = logging.getLogger(__name__)


class GeminiEmbeddingModel(EmbeddingModelAbstraction):
    """
    GeminiEmbeddingModel implementation for LlamaIndex.
    Uses the Gemini API for embeddings.
    """

    def __init__(self, model_name: str):
        """
        Initialize the GeminiEmbeddingModel.

        Args:
            model_name: The name of the Gemini embedding model to use.
        """
        logger.info(f"Loading Gemini embedding model {model_name}...")
        self._model = GeminiEmbedding(
            api_key=config.GEMINI_API_KEY,
            model_name=model_name,
        )

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get the embedding for a single piece of text.
        """
        try:
            return await self._model.aget_text_embedding(text)
        except Exception as e:
            logger.error(f"Failed to get Gemini embedding: {e}", exc_info=True)
            return []

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get the embeddings for a list of texts.
        """
        try:
            return await self._model.aget_text_embedding_batch(texts)
        except Exception as e:
            logger.error(f"Failed to get Gemini embeddings: {e}", exc_info=True)
            return []
