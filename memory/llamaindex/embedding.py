"""
LlamaIndex HuggingFace embedding model implementation.

This module provides the `HuggingFaceEmbeddingModel` class, which implements
the `EmbeddingModel` abstraction using a HuggingFace model from LlamaIndex.
"""

from typing import List
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from core.abstractions import EmbeddingModel as EmbeddingModelAbstraction

class HuggingFaceEmbeddingModel(EmbeddingModelAbstraction):
    """
    HuggingFaceEmbeddingModel implementation for LlamaIndex.
    """

    def __init__(self, model_name: str):
        """
        Initialize the HuggingFaceEmbeddingModel.

        Args:
            model_name: The name of the HuggingFace model to use.
        """
        self._model = HuggingFaceEmbedding(model_name=model_name)

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get the embedding for a single piece of text.

        Args:
            text: The text to embed.

        Returns:
            The embedding vector.
        """
        return self._model.get_text_embedding(text)

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get the embeddings for a list of texts.

        Args:
            texts: The list of texts to embed.

        Returns:
            A list of embedding vectors.
        """
        return self._model.get_text_embedding_batch(texts)