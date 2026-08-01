# /api/app/adapters/outbound/groq_adapter.py
"""
Adaptador Groq - Implementación concreta de LLMPort - TFM Bibliotecario-IA

Este adaptador reemplaza a OllamaAdapter para el despliegue en la nube
(Render free tier), donde no hay GPU ni un proceso Ollama corriendo.

¿Por qué un solo adaptador para dos backends distintos?
LLMPort exige tanto generación de texto (generate_response, extract_keywords)
como embeddings (generate_embedding, generate_embeddings_batch). Groq NO
ofrece un endpoint de embeddings — solo inferencia de chat sobre modelos
open-weight (Llama, gpt-oss, Qwen...) en su hardware LPU.

En vez de partir LLMPort en dos interfaces (lo que obligaría a tocar
RAGService, SyncService y main.py), este adaptador compone dos motores
internamente y expone un único LLMPort, igual que hace OllamaAdapter:
    - Generación de texto  → Groq API (rápida, gratuita, cloud)
    - Embeddings           → sentence-transformers local (CPU, sin API key,
                              sin límite de peticiones, corre en el mismo
                              contenedor de la API)

Esto mantiene el resto del hexágono intacto: RAGService y SyncService no
saben si están hablando con Ollama o con Groq+sentence-transformers.

Nota sobre dimensiones: nomic-embed-text (Ollama) genera vectores de 768
dimensiones; all-MiniLM-L6-v2 (sentence-transformers) genera 384. ChromaDB
infiere la dimensión de la colección del primer chunk insertado, así que
cambiar de adaptador implica re-ingestar los documentos en una colección
nueva (no se puede mezclar embeddings de distinta dimensión en la misma
colección).
"""

from typing import List, Optional, Dict, Any
import asyncio
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from groq import AsyncGroq

from app.core.ports.llm_port import LLMPort
from app.config.settings import settings
from app.core.observability import get_logger, LLM_REQUESTS, LLM_LATENCY

logger = get_logger(__name__)

# Prompt de sistema con las mismas reglas anti-alucinación que usa
# OllamaAdapter.generate_response, para que la calidad de respuesta
# no dependa de qué adaptador esté activo.
_RAG_SYSTEM_PROMPT = """Eres un asistente bibliotecario que SOLO responde usando la información proporcionada en el contexto.

REGLAS ESTRICTAS:
1. SOLO usa la información del contexto para responder
2. NO uses tu conocimiento general o información externa
3. Si la información no está en el contexto, di "No tengo información sobre eso en mi base de conocimientos"
4. Cita las fuentes cuando sea relevante
5. Responde en el mismo idioma que la pregunta"""


class GroqAdapter(LLMPort):
    """
    Implementación de LLMPort que combina Groq (generación) con
    sentence-transformers local (embeddings).

    Mismo patrón de Lazy Singleton que OllamaAdapter: los clientes
    (AsyncGroq, SentenceTransformer) se crean en el primer uso, no en
    __init__, para que la app arranque aunque falte la API key o el
    modelo de embeddings aún no se haya descargado.
    """

    def __init__(self):
        self._client: Optional[AsyncGroq] = None
        self._embedder = None  # SentenceTransformer, tipado perezoso para no importar torch en el arranque

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            if not settings.groq_api_key:
                raise RuntimeError(
                    "GROQ_API_KEY no configurada. Añádela a api/.env "
                    "(consíguela en https://console.groq.com/keys)."
                )
            self._client = AsyncGroq(api_key=settings.groq_api_key)
            logger.info("Initialized Groq client", model=settings.groq_model)
        return self._client

    def _get_embedder(self):
        """
        Carga el modelo de embeddings local (lazy).

        La primera llamada descarga el modelo (~80MB) desde Hugging Face
        si no está en caché; llamadas siguientes reutilizan la instancia.
        Import diferido de sentence_transformers: es una dependencia pesada
        (arrastra torch) que solo hace falta si este adaptador está activo.
        """
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(settings.embedding_model_name)
            logger.info(
                "Initialized local embedding model",
                model=settings.embedding_model_name,
                dimensions=self._embedder.get_sentence_embedding_dimension(),
            )
        return self._embedder

    # ========================================================================
    # Generación de texto (Groq)
    # ========================================================================

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        client = self._get_client()

        messages = [{"role": "system", "content": _RAG_SYSTEM_PROMPT}]
        if context:
            messages.append({
                "role": "user",
                "content": f"CONTEXTO (información de tu base de conocimientos):\n{context}\n\nPREGUNTA DEL USUARIO: {prompt}",
            })
        else:
            messages.append({"role": "user", "content": prompt})

        start_time = time.perf_counter()
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        duration = time.perf_counter() - start_time

        response = completion.choices[0].message.content

        LLM_REQUESTS.labels(operation="generate").inc()
        LLM_LATENCY.labels(operation="generate").observe(duration)
        logger.info("Generated response from Groq", duration_seconds=round(duration, 3), response_length=len(response))

        return response

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def extract_keywords(self, question: str) -> List[str]:
        try:
            client = self._get_client()

            extraction_prompt = (
                "Extrae las palabras clave y nombres propios de esta pregunta.\n"
                "Devuelve SOLO las keywords, una por línea, sin explicaciones ni numeración.\n"
                "Si hay un título de película, libro, o nombre propio, inclúyelo exactamente como aparece.\n\n"
                f"Pregunta: {question}\n\nKeywords:"
            )

            start_time = time.perf_counter()
            completion = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.1,
            )
            duration = time.perf_counter() - start_time

            raw = completion.choices[0].message.content or ""
            keywords = [
                line.strip().strip("-").strip("•").strip()
                for line in raw.strip().split("\n")
            ]
            keywords = [k for k in keywords if len(k) > 2]

            LLM_REQUESTS.labels(operation="extract_keywords").inc()
            LLM_LATENCY.labels(operation="extract_keywords").observe(duration)
            logger.info("Extracted keywords via Groq", keywords=keywords, count=len(keywords))

            return keywords

        except Exception as e:
            logger.warning("Failed to extract keywords via Groq", error=str(e))
            return []

    # ========================================================================
    # Embeddings (sentence-transformers local)
    # ========================================================================

    async def generate_embedding(self, text: str) -> List[float]:
        vectors = await self.generate_embeddings_batch([text])
        return vectors[0]

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        model.encode() es CPU-bound y síncrono: se ejecuta en el executor
        por defecto de asyncio para no bloquear el event loop de FastAPI
        mientras corre (ver LLMPort.generate_embeddings_batch en llm_port.py).
        """
        embedder = self._get_embedder()

        start_time = time.perf_counter()
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(
            None, lambda: embedder.encode(texts, batch_size=32, convert_to_numpy=True)
        )
        duration = time.perf_counter() - start_time

        LLM_REQUESTS.labels(operation="embed_batch").inc()
        LLM_LATENCY.labels(operation="embed_batch").observe(duration)
        logger.info("Generated batch embeddings locally", count=len(texts), duration_seconds=round(duration, 3))

        return vectors.tolist()

    # ========================================================================
    # Utilidades
    # ========================================================================

    async def is_available(self) -> bool:
        """
        Comprueba Groq (llamada ligera a /models) Y que el modelo de
        embeddings local pueda cargarse. Si cualquiera de los dos falla,
        el sistema RAG no puede completar un ciclo pregunta-respuesta.
        """
        if not settings.groq_api_key:
            logger.warning("Groq service unavailable: GROQ_API_KEY not set")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    timeout=5.0,
                )
            if response.status_code != 200:
                logger.warning("Groq returned unexpected status", status_code=response.status_code)
                return False
        except Exception as e:
            logger.error("Groq service unavailable", error=str(e))
            return False

        try:
            self._get_embedder()
        except Exception as e:
            logger.error("Local embedding model unavailable", error=str(e))
            return False

        return True

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "llm_model": settings.groq_model,
            "llm_provider": "groq",
            "embedding_model": settings.embedding_model_name,
            "embedding_provider": "sentence-transformers (local)",
            "base_url": "https://api.groq.com/openai/v1",
        }
