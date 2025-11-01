"""
LlamaIndex embedding model implementations.
"""
import logging
from typing import List
import aiohttp
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from core.abstractions import EmbeddingModel as EmbeddingModelAbstraction

logger = logging.getLogger(__name__)


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


class LMStudioEmbeddingModel(EmbeddingModelAbstraction):
    """
    LMStudioEmbeddingModel implementation for LlamaIndex.
    Uses LM Studio's embedding API for generating embeddings.
    """

    def __init__(self, base_url: str, local_path: str = None):
        """
        Initialize the LMStudioEmbeddingModel.

        Args:
            base_url: The base URL for the LM Studio API (e.g., "http://localhost:1234")
            local_path: Optional local path to a model (for compatibility, not used in API calls)
        """
        self.base_url = base_url.rstrip('/')
        self.local_path = local_path
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _close_session(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get the embedding for a single piece of text using LM Studio API.
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/v1/embeddings"

            payload = {
                "input": text,
                "model": "text-embedding-ada-002"  # LM Studio typically supports OpenAI-compatible endpoints
            }

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"LM Studio API error: {response.status} - {error_text}")

                data = await response.json()
                embedding = data["data"][0]["embedding"]
                return embedding

        except Exception as e:
            logger.error(f"Failed to get embedding from LM Studio: {e}")
            raise

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get the embeddings for a list of texts using LM Studio API.
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/v1/embeddings"

            payload = {
                "input": texts,
                "model": "text-embedding-ada-002"  # LM Studio typically supports OpenAI-compatible endpoints
            }

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"LM Studio API error: {response.status} - {error_text}")

                data = await response.json()
                embeddings = [item["embedding"] for item in data["data"]]
                return embeddings

        except Exception as e:
            logger.error(f"Failed to get embeddings from LM Studio: {e}")
            raise

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_session()