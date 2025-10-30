"""
Core abstractions for the LlamaIndex-based memory system.

This module defines the abstract base classes (ABCs) for the key components
of the memory system, including the vector store, embedding model, and
summarization model. These abstractions allow for a modular and extensible
architecture where different implementations can be swapped without
refactoring the core logic.
"""

from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional

class VectorStore(ABC):
    """
    Abstract base class for a vector store.
    """

    @abstractmethod
    async def upsert(self, nodes: List[Any]) -> None:
        """
        Upsert nodes into the vector store.

        Args:
            nodes: A list of nodes to upsert.
        """
        pass

    @abstractmethod
    async def query(self, query_embedding: List[float], top_k: int) -> List[Any]:
        """
        Query the vector store for similar nodes.

        Args:
            query_embedding: The query embedding.
            top_k: The number of top results to return.

        Returns:
            A list of similar nodes.
        """
        pass

    @abstractmethod
    async def clear(self, user_id: str) -> None:
        """
        Clear all nodes for a specific user from the vector store.

        Args:
            user_id: The ID of the user whose data should be cleared.
        """
        pass


class EmbeddingModel(ABC):
    """
    Abstract base class for an embedding model.
    """

    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """
        Get the embedding for a single piece of text.

        Args:
            text: The text to embed.

        Returns:
            The embedding vector.
        """
        pass

    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get the embeddings for a list of texts.

        Args:
            texts: The list of texts to embed.

        Returns:
            A list of embedding vectors.
        """
        pass


class SummarizationModel(ABC):
    """
    Abstract base class for a summarization model.
    """

    @abstractmethod
    async def summarize(self, text: str, prompt_template: str, user_id: Optional[str] = None) -> str:
        """
        Summarize a piece of text.

        Args:
            text: The text to summarize.
            prompt_template: The prompt template to use for summarization.
            user_id: The optional ID of the user.

        Returns:
            The summarized text.
        """
        pass