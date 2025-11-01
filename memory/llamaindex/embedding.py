"""
LlamaIndex LM Studio embedding model implementation.
"""
from typing import List
from llama_index.embeddings.openai import OpenAIEmbedding
from core.abstractions import EmbeddingModel as EmbeddingModelAbstraction

class LMStudioEmbeddingModel(EmbeddingModelAbstraction):
    """
    LMStudioEmbeddingModel implementation for LlamaIndex.
    Uses OpenAIEmbedding pointed at a local LM Studio instance.
    """

    def __init__(self, model_name: str = None, base_url: str = None, api_key: str = "not-needed", local_path: str = None):
        """
        Initialize the LMStudioEmbeddingModel.

        Args:
            model_name: The name of the embedding model to use in LM Studio.
            base_url: The base URL of the LM Studio server.
            api_key: The API key (usually not needed for local LM Studio).
            local_path: Optional path to local SentenceTransformer model directory.
        """
        if local_path:
            # Use local SentenceTransformer model
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            self._model = HuggingFaceEmbedding(model_name=local_path)
        else:
            # Use LM Studio API - convert chat completions URL to embeddings URL
            embeddings_url = base_url.replace("/chat/completions", "/embeddings") if base_url else None
            self._model = OpenAIEmbedding(
                model=model_name,
                api_base=embeddings_url,
                api_key=api_key,
            )

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get the embedding for a single piece of text.
        """
        return self._model.get_text_embedding(text)

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get the embeddings for a list of texts.
        """
        return self._model.get_text_embedding_batch(texts)