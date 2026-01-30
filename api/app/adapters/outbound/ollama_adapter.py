# /api/app/adapters/outbound/ollama_adapter.py

"""
Ollama adapter implementation for LLM operations.
Uses langchain-ollama for integration.
"""

from typing import List, Optional, Dict, Any
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from langchain_ollama import OllamaLLM, OllamaEmbeddings

from app.core.ports.llm_port import LLMPort
from app.config.settings import settings


logger = logging.getLogger(__name__)


class OllamaAdapter(LLMPort):
    """Ollama implementation of the LLMPort interface."""

    def __init__(self):
        """Initialize Ollama clients for LLM and embeddings."""
        self._llm = None
        self._embeddings = None

    def _get_llm(self) -> OllamaLLM:
        """Get or create Ollama LLM instance."""
        if self._llm is None:
            try:
                self._llm = OllamaLLM(
                    base_url=settings.ollama_base_url,
                    model=settings.ollama_model,
                    temperature=settings.llm_temperature,
                    timeout=settings.ollama_timeout
                )
                logger.info(f"Initialized Ollama LLM with model: {settings.ollama_model}")
            except Exception as e:
                logger.error(f"Failed to initialize Ollama LLM: {e}")
                raise
        return self._llm

    def _get_embeddings(self) -> OllamaEmbeddings:
        """Get or create Ollama Embeddings instance."""
        if self._embeddings is None:
            try:
                self._embeddings = OllamaEmbeddings(
                    base_url=settings.ollama_base_url,
                    model=settings.ollama_embedding_model
                )
                logger.info(f"Initialized Ollama Embeddings with model: {settings.ollama_embedding_model}")
            except Exception as e:
                logger.error(f"Failed to initialize Ollama Embeddings: {e}")
                raise
        return self._embeddings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate text response from Ollama."""
        try:
            llm = self._get_llm()

            # Build the full prompt with context if provided
            if context:
                full_prompt = f"""Context information:
{context}

Question: {prompt}

Answer based on the context above:"""
            else:
                full_prompt = prompt

            # Generate response
            response = await llm.ainvoke(
                full_prompt,
                temperature=temperature,
                **kwargs
            )

            logger.info("Generated response from Ollama")
            return response

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        try:
            embeddings = self._get_embeddings()
            embedding = await embeddings.aembed_query(text)
            logger.debug(f"Generated embedding of dimension: {len(embedding)}")
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        try:
            embeddings = self._get_embeddings()
            embedding_vectors = await embeddings.aembed_documents(texts)
            logger.info(f"Generated {len(embedding_vectors)} embeddings")
            return embedding_vectors

        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise

    async def is_available(self) -> bool:
        """Check if Ollama service is available."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.ollama_base_url}/api/tags",
                    timeout=5.0
                )
                if response.status_code == 200:
                    logger.info("Ollama service is available")
                    return True
                else:
                    logger.warning(f"Ollama returned status code: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Ollama service unavailable: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about current Ollama models."""
        return {
            "llm_model": settings.ollama_model,
            "embedding_model": settings.ollama_embedding_model,
            "base_url": settings.ollama_base_url,
            "temperature": settings.llm_temperature,
            "timeout": settings.ollama_timeout
        }
