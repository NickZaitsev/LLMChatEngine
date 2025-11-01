"""
LlamaIndex HuggingFace embedding model implementation.
"""
from typing import List
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from core.abstractions import EmbeddingModel as EmbeddingModelAbstraction

class HuggingFaceEmbeddingModel(EmbeddingModelAbstraction):
    """
    HuggingFaceEmbeddingModel implementation for LlamaIndex.
    Uses a local HuggingFace SentenceTransformer model.
    """

    def __init__(self, model_path: str):
        """
        Initialize the HuggingFaceEmbeddingModel.

        Args:
            model_path: The path to a local HuggingFace SentenceTransformer model directory.
        """
        self._model = HuggingFaceEmbedding(model_name=model_path)

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