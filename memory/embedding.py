"""
Embedding utilities for memory management.

This module provides utilities to load embedding models, batch-encode texts,
and normalize vectors using sentence-transformers.
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

# Global model cache to avoid reloading
_model_cache: Dict[str, Any] = {}
_model_lock = threading.Lock()
_executor: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    """Get or create thread executor for CPU-bound embedding tasks."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedding")
    return _executor


def _load_model(model_name: str) -> Any:
    """
    Load a sentence-transformers model with caching.
    
    Args:
        model_name: Name/path of the sentence-transformers model
        
    Returns:
        Loaded SentenceTransformer model
        
    Raises:
        ImportError: If sentence-transformers is not installed
        Exception: If model loading fails
    """
    with _model_lock:
        if model_name not in _model_cache:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {model_name}")
                model = SentenceTransformer(model_name)
                _model_cache[model_name] = model
                logger.info(f"Successfully loaded model: {model_name}")
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for embedding functionality. "
                    "Install it with: pip install sentence-transformers"
                )
            except Exception as e:
                logger.error(f"Failed to load embedding model {model_name}: {e}")
                raise
        
        return _model_cache[model_name]


def _encode_batch(model_name: str, texts: List[str], normalize: bool = True) -> List[List[float]]:
    """
    Encode a batch of texts using the specified model.
    
    This function runs in a thread executor to avoid blocking the async loop.
    
    Args:
        model_name: Name of the model to use
        texts: List of texts to encode
        normalize: Whether to normalize the vectors
        
    Returns:
        List of embedding vectors as float lists
    """
    if not texts:
        return []
    
    model = _load_model(model_name)
    
    try:
        # Encode texts in batch for efficiency
        embeddings = model.encode(
            texts,
            batch_size=min(32, len(texts)),  # Reasonable batch size
            show_progress_bar=False,
            convert_to_tensor=False,  # Return numpy arrays
            normalize_embeddings=normalize
        )
        
        # Convert numpy arrays to Python lists for JSON serialization
        if isinstance(embeddings, np.ndarray):
            return embeddings.astype(np.float32).tolist()
        else:
            return [emb.astype(np.float32).tolist() if isinstance(emb, np.ndarray) else emb 
                   for emb in embeddings]
    
    except Exception as e:
        logger.error(f"Failed to encode batch of {len(texts)} texts: {e}")
        raise


async def embed_texts(
    texts: List[str], 
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    normalize: bool = True,
    batch_size: int = 100
) -> List[List[float]]:
    """
    Asynchronously encode texts into embedding vectors.
    
    This function batches the encoding process and runs it in a thread executor
    to avoid blocking the async event loop.
    
    Args:
        texts: List of texts to encode
        model_name: Name/path of the sentence-transformers model to use
        normalize: Whether to normalize the embedding vectors
        batch_size: Maximum batch size for processing
        
    Returns:
        List of embedding vectors, each as a list of floats
        
    Raises:
        ImportError: If sentence-transformers is not installed
        ValueError: If texts list is empty or contains invalid data
        
    Examples:
        >>> embeddings = await embed_texts(["Hello world", "How are you?"])
        >>> len(embeddings)
        2
        >>> len(embeddings[0])  # Should be 384 for all-MiniLM-L6-v2
        384
    """
    if not texts:
        return []
    
    if not all(isinstance(text, str) for text in texts):
        raise ValueError("All texts must be strings")
    
    # Filter out empty texts but preserve indices
    non_empty_texts = []
    text_indices = []
    
    for i, text in enumerate(texts):
        if text and text.strip():
            non_empty_texts.append(text.strip())
            text_indices.append(i)
    
    if not non_empty_texts:
        logger.warning("All input texts are empty, returning zero vectors")
        # Return zero vectors with appropriate dimensions
        model = _load_model(model_name)
        embedding_dim = model.get_sentence_embedding_dimension()
        return [[0.0] * embedding_dim for _ in texts]
    
    logger.debug(f"Encoding {len(non_empty_texts)} texts with model {model_name}")
    
    # Process in batches to manage memory usage
    all_embeddings = []
    executor = _get_executor()
    
    for i in range(0, len(non_empty_texts), batch_size):
        batch_texts = non_empty_texts[i:i + batch_size]
        
        # Run encoding in thread executor
        batch_embeddings = await asyncio.get_event_loop().run_in_executor(
            executor, _encode_batch, model_name, batch_texts, normalize
        )
        
        all_embeddings.extend(batch_embeddings)
    
    # Reconstruct full results with zero vectors for empty texts
    result = []
    embedding_dim = len(all_embeddings[0]) if all_embeddings else 384
    embedding_idx = 0
    
    for i, text in enumerate(texts):
        if i in text_indices:
            result.append(all_embeddings[embedding_idx])
            embedding_idx += 1
        else:
            # Zero vector for empty text
            result.append([0.0] * embedding_dim)
    
    logger.debug(f"Successfully encoded {len(texts)} texts")
    return result


async def embed_single_text(
    text: str,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    normalize: bool = True
) -> List[float]:
    """
    Encode a single text into an embedding vector.
    
    This is a convenience function for single text encoding.
    
    Args:
        text: Text to encode
        model_name: Name/path of the sentence-transformers model to use
        normalize: Whether to normalize the embedding vector
        
    Returns:
        Embedding vector as a list of floats
        
    Examples:
        >>> embedding = await embed_single_text("Hello world")
        >>> len(embedding)  # Should be 384 for all-MiniLM-L6-v2
        384
    """
    embeddings = await embed_texts([text], model_name, normalize)
    return embeddings[0]


def get_model_info(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> Dict[str, Any]:
    """
    Get information about an embedding model.
    
    Args:
        model_name: Name/path of the sentence-transformers model
        
    Returns:
        Dictionary with model information including dimensions
        
    Raises:
        ImportError: If sentence-transformers is not installed
    """
    model = _load_model(model_name)
    
    return {
        "model_name": model_name,
        "embedding_dimension": model.get_sentence_embedding_dimension(),
        "max_seq_length": getattr(model, 'max_seq_length', None),
        "device": str(model.device) if hasattr(model, 'device') else None,
    }


def cleanup_models():
    """Clear the model cache and clean up resources."""
    global _model_cache, _executor
    
    with _model_lock:
        _model_cache.clear()
    
    if _executor:
        _executor.shutdown(wait=True)
        _executor = None
    
    logger.info("Cleaned up embedding models and resources")


# Export public API
__all__ = [
    'embed_texts',
    'embed_single_text', 
    'get_model_info',
    'cleanup_models'
]