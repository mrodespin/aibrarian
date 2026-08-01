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
    Implementación de LLMPort que combina Groq (generación) con el
    embedder ONNX local de ChromaDB (embeddings).

    Mismo patrón de Lazy Singleton que OllamaAdapter: los clientes
    (AsyncGroq, ONNXMiniLM_L6_V2) se crean en el primer uso, no en
    __init__, para que la app arranque aunque falte la API key o el
    modelo de embeddings aún no se haya descargado.
    """

    def __init__(self):
        self._client: Optional[AsyncGroq] = None
        self._embedder = None  # ONNXMiniLM_L6_V2, tipado perezoso para no importar onnxruntime en el arranque

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
        Carga el modelo de embeddings local (lazy), según settings.embedding_backend:

        - 'onnx' (default): chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2,
          mismo modelo (all-MiniLM-L6-v2, 384 dims, mean pooling + normalización
          L2) pero vía onnxruntime, que ya es dependencia transitiva de chromadb.
          No añade nada a requirements.txt. Recomendado para Render free tier:
          torch+transformers (backend 'sentence_transformers') por sí solos
          añaden ~650MB en disco y suficiente RAM en el import como para
          provocar un OOM (512MB) antes de atender ninguna petición real.
        - 'sentence_transformers': requiere `pip install sentence-transformers`
          aparte (deliberadamente fuera de requirements.txt, ver ahí el porqué).
          Pensado para desarrollo local con más RAM disponible.

        La primera llamada descarga el modelo si no está en caché (ver
        Dockerfile, que lo pre-descarga en el build); llamadas siguientes
        reutilizan la instancia.
        """
        if self._embedder is None:
            if settings.embedding_backend == "sentence_transformers":
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as e:
                    raise RuntimeError(
                        "EMBEDDING_BACKEND=sentence_transformers pero el paquete "
                        "no está instalado (deliberadamente no está en requirements.txt, "
                        "ver comentario ahí). Instálalo con `pip install sentence-transformers` "
                        "o cambia EMBEDDING_BACKEND=onnx."
                    ) from e
                self._embedder = SentenceTransformer(settings.embedding_model_name)
                logger.info(
                    "Initialized local embedding model (sentence-transformers)",
                    model=settings.embedding_model_name,
                    dimensions=self._embedder.get_sentence_embedding_dimension(),
                )
            else:
                from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                self._embedder = ONNXMiniLM_L6_V2()
                logger.info("Initialized local embedding model (ONNX)", model=settings.embedding_model_name)
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
    # Embeddings (local, backend configurable — ver _get_embedder)
    # ========================================================================

    async def generate_embedding(self, text: str) -> List[float]:
        vectors = await self.generate_embeddings_batch([text])
        return vectors[0]

    @staticmethod
    def _encode_sync(embedder, texts: List[str]) -> List[List[float]]:
        """
        Encapsula la llamada CPU-bound al embedder (se ejecuta en un executor,
        ver generate_embeddings_batch). Las dos librerías exponen una API
        distinta pese a producir el mismo tipo de vector (384 floats
        normalizados): sentence-transformers usa .encode(...) y devuelve un
        único array 2D; ONNXMiniLM_L6_V2 se invoca directamente (__call__) y
        devuelve una lista de arrays 1D, uno por texto.
        """
        if settings.embedding_backend == "sentence_transformers":
            vectors = embedder.encode(texts, batch_size=32, convert_to_numpy=True)
            return vectors.tolist()
        return [vector.tolist() for vector in embedder(texts)]

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        embedder = self._get_embedder()

        start_time = time.perf_counter()
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(None, self._encode_sync, embedder, texts)
        duration = time.perf_counter() - start_time

        LLM_REQUESTS.labels(operation="embed_batch").inc()
        LLM_LATENCY.labels(operation="embed_batch").observe(duration)
        logger.info("Generated batch embeddings locally", count=len(texts), duration_seconds=round(duration, 3))

        return vectors

    # ========================================================================
    # Utilidades
    # ========================================================================

    async def is_available(self) -> bool:
        """
        Comprueba solo Groq (llamada ligera a /models).

        Deliberadamente NO carga aquí el modelo de embeddings local: esta
        función se llama en el startup de FastAPI (ver lifespan en main.py),
        y uvicorn no empieza a escuchar en el puerto hasta que el startup
        termina. Cargar sentence-transformers aquí (síncrono, sin timeout,
        puede implicar descargar el modelo de Hugging Face) bloqueaba el
        arranque el tiempo suficiente para que Render diera el deploy por
        timeout ("no open ports detected") antes de que el puerto llegara
        a abrirse. El modelo de embeddings se sigue cargando de forma lazy
        en el primer uso real (_get_embedder), como indica su docstring.
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

        return True

    async def warm_up(self) -> None:
        """
        Precarga el modelo de embeddings local en un hilo aparte para que
        la primera petición real (sync o chat) no pague el coste de
        cargarlo. Se ejecuta como tarea en segundo plano tras el arranque
        (ver main.py), así que un fallo aquí no debe tumbar la app: si algo
        va mal, _get_embedder() se reintentará de forma lazy en el primer
        uso real y ese error sí se propagará al endpoint correspondiente.
        """
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._get_embedder)
        except Exception as e:
            logger.warning("Embedding model warm-up failed, will retry lazily on first use", error=str(e))

    def get_model_info(self) -> Dict[str, Any]:
        embedding_provider = (
            "sentence-transformers (local)"
            if settings.embedding_backend == "sentence_transformers"
            else "onnxruntime (local, via chromadb)"
        )
        return {
            "llm_model": settings.groq_model,
            "llm_provider": "groq",
            "embedding_model": settings.embedding_model_name,
            "embedding_provider": embedding_provider,
            "base_url": "https://api.groq.com/openai/v1",
        }
