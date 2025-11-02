"""
LlamaIndex embedding model implementations.
"""
import logging
from typing import List
import numpy as np
from llama_index.llms.lmstudio import LMStudio
from core.abstractions import EmbeddingModel as EmbeddingModelAbstraction
import config

logger = logging.getLogger(__name__)


class LMStudioEmbeddingModel(EmbeddingModelAbstraction):
    """
    LMStudioEmbeddingModel implementation for LlamaIndex.
    Uses a local LMStudio model.
    """

    def __init__(self, model_path: str):
        """
        Initialize the LMStudioEmbeddingModel.

        Args:
            model_path: The path to a local LMStudio model directory.
        """
        logger.info(f"Loading local LMStudio model from {model_path}...")
        self._model = LMStudio(
            model_name=model_path,
            base_url=config.LMSTUDIO_BASE_URL.rstrip('/')+"/embeddings/",
            temperature=config.TEMPERATURE,
        )

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get the embedding for a single piece of text.
        """
        # Await the async call from the underlying model
        return await self._model.aget_text_embedding(text)

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get the embeddings for a list of texts.
        """
        # Await the async call from the underlying model
        return await self._model.aget_text_embedding_batch(texts)