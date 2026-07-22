"""
Core abstractions for the LlamaIndex-based memory system.

This module defines the abstract base classes (ABCs) for the key components
of the memory system, including the vector store, embedding model, and
summarization model. These abstractions allow for a modular and extensible
architecture where different implementations can be swapped without
refactoring the core logic.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Protocol


class VectorStore(ABC):
    """
    Abstract base class for a vector store.
    """

    @abstractmethod
    async def upsert(self, nodes: list[Any]) -> None:
        """
        Upsert nodes into the vector store.

        Args:
            nodes: A list of nodes to upsert.
        """
        pass

    @abstractmethod
    async def query(self, query_embedding: list[float], top_k: int, user_id: str) -> list[Any]:
        """
        Query the vector store for similar nodes.

        Args:
            query_embedding: The query embedding.
            top_k: The number of top results to return.
            user_id: The ID of the user to filter memories for.

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


class KnowledgeStore(Protocol):
    """Bot-scoped vector store contract for immutable reference knowledge."""

    async def upsert(self, nodes: list[Any]) -> None:
        """Upsert knowledge nodes into the store."""
        ...

    async def query(
        self,
        query_embedding: list[float],
        top_k: int,
        bot_id: str,
        min_score: float | None = None,
    ) -> list[Any]:
        """Query similar knowledge nodes scoped to a bot."""
        ...

    async def delete_book(self, book_id: str) -> None:
        """Delete all nodes for a specific book."""
        ...


class EmbeddingModel(ABC):
    """
    Abstract base class for an embedding model.
    """

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """
        Get the embedding for a single piece of text.

        Args:
            text: The text to embed.

        Returns:
            The embedding vector.
        """
        pass

    @abstractmethod
    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
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
    async def summarize(self, text: str, prompt_template: str, user_id: str | None = None) -> str:
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
