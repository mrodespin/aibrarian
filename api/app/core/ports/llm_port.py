# /api/app/core/ports/llm_port.py

"""
Port (interface) for Language Model operations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class LLMPort(ABC):
    """Abstract interface for Language Model operations."""

    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Generate a text response from the language model.

        Args:
            prompt: The user's question or prompt
            context: Optional context to include in the prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0 to 1.0)
            **kwargs: Additional model-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate vector embedding for text.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        pass

    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the LLM service is available and responding.

        Returns:
            True if available, False otherwise
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current model.

        Returns:
            Dictionary with model name, version, capabilities, etc.
        """
        pass
